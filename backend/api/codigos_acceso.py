"""Servicio del código de acceso por mail: genera, reenvía, vence y quema.

Implementa RF6, RF9 y RF16 del plan de puertas de acceso. La regla que la
crítica encontró rota: pedir un código nuevo cuando ya hay uno vigente lo
REENVÍA en vez de regenerarlo. Si lo regenerara, cualquiera que supiera tu
dirección podría pedir códigos en loop y matar el que estás tipeando.
"""
import hmac
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from api.identity import hash_token
from api.models import CodigoAcceso

logger = logging.getLogger(__name__)


class CodigoInvalido(Exception):
    """No coincide, venció, se quemó o ya se usó. Un solo motivo hacia afuera:
    decir cuál de los cuatro es ayudarle a quien está probando."""


class DemasiadosPedidos(Exception):
    pass


def normalizar(email: str) -> str:
    # Minúsculas y trim, nada más. Sacar los puntos de Gmail está mal para
    # cualquier otro proveedor y es un pozo sin fondo.
    return email.strip().lower()


def _nuevo_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def pedir(email: str, destino: str = "") -> tuple[CodigoAcceso, str, bool]:
    """Devuelve (fila, código EN CLARO, si fue reenvío).

    Si ya hay uno vigente lo REENVÍA en vez de regenerarlo: regenerarlo abría
    una denegación de acceso —quien supiera la dirección podía pedir códigos en
    loop y matar el que la persona estaba tipeando—.
    """
    email = normalizar(email)
    ahora = timezone.now()
    hace_una_hora = ahora - timezone.timedelta(hours=1)
    if CodigoAcceso.objects.filter(
        email=email, creado_en__gte=hace_una_hora,
    ).count() >= settings.CODIGO_PEDIDOS_HORA:
        raise DemasiadosPedidos

    with transaction.atomic():
        fila = CodigoAcceso.objects.select_for_update().filter(
            email=email, usado_en__isnull=True,
        ).first()

        if fila is not None and fila.expira_en <= ahora:
            # La constraint parcial sólo mira `usado_en IS NULL`, no
            # "vigente": Postgres no acepta now() en la condición de un
            # índice, así que un código YA EXPIRADO y sin usar sigue
            # bloqueando la fila única. Se descarta acá, antes de crear el
            # nuevo, o el create de abajo revienta con IntegrityError.
            fila.usado_en = ahora
            fila.save(update_fields=["usado_en"])
            fila = None

        if fila is not None:
            # El claro no se guardó nunca, así que no se puede releer: se
            # manda uno nuevo y se re-hashea la MISMA fila, que conserva el
            # contador de intentos y el vencimiento original — el pedido
            # repetido no le regala a nadie cinco intentos nuevos ni diez
            # minutos más.
            claro = _nuevo_codigo()
            fila.codigo_hash = hash_token(claro)
            fila.save(update_fields=["codigo_hash"])
            return fila, claro, True

        claro = _nuevo_codigo()
        fila = CodigoAcceso.objects.create(
            email=email,
            codigo_hash=hash_token(claro),
            destino=destino,
            expira_en=ahora + timezone.timedelta(minutes=settings.CODIGO_TTL_MINUTOS),
        )
    return fila, claro, False


def canjear(email: str, codigo: str) -> CodigoAcceso:
    email = normalizar(email)
    ahora = timezone.now()
    with transaction.atomic():
        fila = CodigoAcceso.objects.select_for_update().filter(
            email=email, usado_en__isnull=True,
        ).first()
        if fila is None or fila.expira_en <= ahora:
            raise CodigoInvalido
        if fila.intentos >= settings.CODIGO_INTENTOS_MAX:
            raise CodigoInvalido
        # El intento se cobra ANTES de comparar: si no, un fallo se puede
        # reintentar sin costo y el techo no frena nada. Ojo: el `save` tiene
        # que quedar DENTRO del atomic pero el `raise` de un mal match tiene
        # que quedar AFUERA — levantar la excepción con el atomic todavía
        # abierto hace rollback de todo el bloque, este incremento incluido,
        # y el techo de intentos nunca se cobra de verdad.
        fila.intentos += 1
        fila.save(update_fields=["intentos"])
        coincide = hmac.compare_digest(fila.codigo_hash, hash_token(codigo))
        if coincide:
            fila.usado_en = ahora
            fila.save(update_fields=["usado_en"])
    if not coincide:
        logger.info("código de acceso rechazado", extra={"intentos": fila.intentos})
        raise CodigoInvalido
    return fila
