"""Servicio del código de acceso por mail: genera, reenvía, vence y quema.

Implementa RF6, RF9 y RF16 del plan de puertas de acceso. La regla que la
crítica encontró rota: pedir un código nuevo cuando ya hay uno vigente lo
REENVÍA en vez de regenerarlo. Si lo regenerara, cualquiera que supiera tu
dirección podría pedir códigos en loop y matar el que estás tipeando.
"""
import hmac
import logging
import secrets
import unicodedata

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from api.identity import hash_token, normalizar
from api.models import CodigoAcceso

logger = logging.getLogger(__name__)


class CodigoInvalido(Exception):
    """No coincide, venció, se quemó o ya se usó. Un solo motivo hacia afuera:
    decir cuál de los cuatro es ayudarle a quien está probando."""


class DemasiadosPedidos(Exception):
    pass


# Categorías Unicode que no tienen nada que hacer en un path: Cc (control,
# \x00-\x1f, \x7f-\x9f...), Cf (formato invisible: RTL override y afines,
# clásicos para disfrazar un path) y Zl/Zp (separadores de línea/párrafo,
# U+2028/U+2029 — no son \s en todos lados pero sí caracteres de control a
# efectos de esto). Categoría en vez de un rango ASCII a mano: el rango
# original (`[\x00-\x1f\x7f]`) dejaba pasar todo el bloque C1
# (\x80-\x9f) y estos separadores.
_CATEGORIAS_PELIGROSAS = {"Cc", "Cf", "Zl", "Zp"}


def _tiene_caracteres_peligrosos(destino: str) -> bool:
    return any(unicodedata.category(c) in _CATEGORIAS_PELIGROSAS for c in destino)


def _destino_seguro(destino: str) -> str:
    """Sólo un path interno vale como destino post-login (Ruling 16).

    `destino` lo manda quien llama a `pedir()` sin pasar por ninguna
    autenticación, y la web lo va a usar para redirigir después de loguear:
    sin esta validación, `destino=https://phishing.example` convierte el
    login por mail en un open redirect post-autenticación.

    Se acepta sólo un path interno —empieza con "/", no con "//" ni con
    "/\\", sin backslashes ni caracteres de control (ASCII o Unicode), hasta
    200 caracteres—. Cualquier otra cosa se guarda vacía, sin rechazar el
    pedido: el login tiene que seguir funcionando, sólo se pierde el atajo de
    volver adonde estaba.
    """
    if not destino:
        return ""
    if len(destino) > 200:
        return ""
    if not destino.startswith("/"):
        return ""
    if destino.startswith("//") or destino.startswith("/\\"):
        return ""
    if "\\" in destino:
        return ""
    if _tiene_caracteres_peligrosos(destino):
        return ""
    return destino


def _nuevo_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _reenviar(fila: CodigoAcceso, destino: str) -> str:
    """Re-hashea un código nuevo sobre una fila existente y la cuenta como un
    envío más. El claro no se guardó nunca, así que no se puede releer: se
    manda uno nuevo y se conserva el contador de intentos y el vencimiento
    original — el pedido repetido no le regala a nadie cinco intentos nuevos
    ni diez minutos más.

    El `destino` sólo se pisa cuando el pedido nuevo trae uno (Ruling 10): un
    reenvío sin `destino` explícito conserva a dónde tenía que volver la
    persona, uno CON `destino` lo actualiza — si no, RF16 vuelve a mandarla a
    la página vieja después de entrar, que es el mismo bug que RF16 vino a
    cerrar.
    """
    claro = _nuevo_codigo()
    fila.codigo_hash = hash_token(claro)
    fila.envios += 1
    update_fields = ["codigo_hash", "envios"]
    if destino:
        fila.destino = destino
        update_fields.append("destino")
    fila.save(update_fields=update_fields)
    return claro


def pedir(email: str, destino: str = "") -> tuple[CodigoAcceso, str, bool]:
    """Devuelve (fila, código EN CLARO, si fue reenvío).

    Si ya hay uno vigente lo REENVÍA en vez de regenerarlo: regenerarlo abría
    una denegación de acceso —quien supiera la dirección podía pedir códigos en
    loop y matar el que la persona estaba tipeando—.
    """
    email = normalizar(email)
    destino = _destino_seguro(destino)
    ahora = timezone.now()
    hace_una_hora = ahora - timezone.timedelta(hours=1)
    # El techo cuenta ENVÍOS (mails salidos), no filas: un reenvío no crea
    # fila nueva, así que contar filas dejaba pedir en loop contra una
    # dirección ajena sin tocar el techo mientras el código vigente no
    # venciera (hasta CODIGO_TTL_MINUTOS). La carrera acá es benigna a
    # propósito: no hay fila que lockear en este camino y dos pedidos
    # simultáneos podrían dejar pasar un envío de más — un mail extra no hace
    # daño y serializar esto no vale el costo.
    enviados = CodigoAcceso.objects.filter(
        email=email, creado_en__gte=hace_una_hora,
    ).aggregate(total=Coalesce(Sum("envios"), 0))["total"]
    if enviados >= settings.CODIGO_PEDIDOS_HORA:
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
            claro = _reenviar(fila, destino)
            return fila, claro, True

        try:
            # Savepoint anidado: sin fila previa, `select_for_update()` de
            # arriba no bloqueó nada —no hay fila que lockear— así que dos
            # pedidos casi a la vez (doble clic, dos pestañas) para la misma
            # dirección sin código vigente entran los dos acá. Postgres deja
            # pasar uno y el otro choca con la UniqueConstraint parcial: en
            # Postgres ese IntegrityError invalida la transacción entera, y
            # sin este savepoint no se podría seguir operando en el bloque
            # exterior para degradarlo a reenvío.
            with transaction.atomic():
                claro = _nuevo_codigo()
                fila = CodigoAcceso.objects.create(
                    email=email,
                    codigo_hash=hash_token(claro),
                    destino=destino,
                    expira_en=ahora + timezone.timedelta(minutes=settings.CODIGO_TTL_MINUTOS),
                )
        except IntegrityError:
            # Se perdió la carrera del create(): la fila que ganó ya existe,
            # así que esto es exactamente lo mismo que si este pedido hubiera
            # llegado 5ms más tarde — se degrada a reenvío sobre la fila
            # ganadora. Log estructurado sin email ni código en claro. Si la
            # relectura no encuentra nada (¿la borraron entre medio?), no se
            # silencia: propaga, que es el mismo 500 de antes y no uno peor.
            logger.warning("pedido de código chocó con uno concurrente, degradado a reenvío")
            fila = CodigoAcceso.objects.select_for_update().filter(
                email=email, usado_en__isnull=True,
            ).first()
            if fila is None:
                raise
            claro = _reenviar(fila, destino)
            return fila, claro, True

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
