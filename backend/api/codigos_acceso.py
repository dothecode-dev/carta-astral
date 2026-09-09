"""Servicio del código de acceso por mail: genera, vence y quema.

Implementa RF6, RF9 y RF16 del plan de puertas de acceso, corregido con el
Hallazgo I1 de la revisión final: pedir un código nuevo mientras hay uno
vigente solía REENVIAR el mismo (re-hashear la fila), y eso invalidaba el
código que la persona estaba tipeando. Regenerarlo directamente era peor —
cualquiera que supiera tu dirección podría pedir códigos en loop y matar el
que estás tipeando— así que la solución no es "cuál de los dos": es que
convivan varios códigos vigentes por dirección. Cada `pedir()` crea una fila
nueva y ninguna existente se toca; todas sirven hasta que vencen o se
canjean. El código NUNCA se guarda en claro, así que no hay nada que
"reenviar" en el sentido de releer un secreto: cada pedido es, literalmente,
un código nuevo — la persona sólo ve que le llegó "otro mail más" y puede
usar cualquiera de los que tenga en la bandeja.

Con varias filas vigentes por dirección, dos invariantes que antes vivían en
la fila pasan a vivir en la DIRECCIÓN (ver `canjear()`): el techo de intentos
de RF9 (si no, tres códigos vigentes serían tres veces cinco intentos) y "un
canje bueno quema todo lo demás vigente" (si no, un mail viejo seguiría
sirviendo después de que la persona ya entró).
"""
import hmac
import logging
import secrets
import unicodedata
from typing import Callable

from django.conf import settings
from django.db import transaction
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


def pedir(email: str, destino: str = "") -> tuple[CodigoAcceso, str, bool]:
    """Devuelve (fila nueva, código EN CLARO, si ya había uno vigente antes).

    Siempre crea una fila nueva con un código nuevo: ninguna fila existente se
    toca, así que un código vigente que la persona esté tipeando nunca se
    invalida por pedir otro (Hallazgo I1). El tercer valor no cambia el
    comportamiento — es informativo, por si a quien llama le sirve saber que
    esto es "otro mail más" y no el primero.

    Sin una fila única por dirección no hay nada que lockear ni ninguna
    carrera que perder acá: dos pedidos a la vez para la misma dirección
    simplemente crean dos filas, las dos vigentes, sin choque posible.
    """
    email = normalizar(email)
    destino = _destino_seguro(destino)
    ahora = timezone.now()
    hace_una_hora = ahora - timezone.timedelta(hours=1)
    # El techo cuenta ENVÍOS (mails salidos), no filas — hoy son lo mismo (una
    # fila nueva por pedido, `envios` arranca en 1), pero se mantiene como
    # suma porque `PedirCodigoView` resta 1 sobre una fila puntual cuando el
    # envío falla (Ruling 13), y esa resta tiene que seguir contando acá. La
    # carrera de esta lectura es benigna a propósito: no hay fila que
    # lockear en este camino y dos pedidos simultáneos podrían dejar pasar un
    # envío de más — un mail extra no hace daño y serializar esto no vale el
    # costo.
    enviados = CodigoAcceso.objects.filter(
        email=email, creado_en__gte=hace_una_hora,
    ).aggregate(total=Coalesce(Sum("envios"), 0))["total"]
    if enviados >= settings.CODIGO_PEDIDOS_HORA:
        raise DemasiadosPedidos

    vigente_previo = CodigoAcceso.objects.filter(
        email=email, usado_en__isnull=True, expira_en__gt=ahora,
    ).order_by("-pk").first()

    # El `destino` sólo se pisa cuando el pedido nuevo trae uno (Ruling 10):
    # un pedido sin `destino` explícito hereda a dónde tenía que volver la
    # persona del código vigente más reciente, uno CON `destino` lo define
    # para la fila nueva — si no, RF16 vuelve a mandarla a la página vieja
    # después de entrar, que es el mismo bug que RF16 vino a cerrar.
    if not destino and vigente_previo is not None:
        destino = vigente_previo.destino

    claro = _nuevo_codigo()
    fila = CodigoAcceso.objects.create(
        email=email,
        codigo_hash=hash_token(claro),
        destino=destino,
        expira_en=ahora + timezone.timedelta(minutes=settings.CODIGO_TTL_MINUTOS),
    )
    return fila, claro, vigente_previo is not None


def canjear(
    email: str, codigo: str, despues_de_marcar: Callable[[CodigoAcceso], None] | None = None,
) -> CodigoAcceso:
    """Con varios códigos vigentes por dirección, dos cosas que antes vivían
    en LA fila pasan a vivir en la DIRECCIÓN:

    - El techo de intentos de RF9 (Hallazgo 1 de la re-revisión de
      `puertas-de-acceso`, corregido): el intento se cobra en UNA sola fila
      (la más vieja, `vigentes[0]`) y no en todas — cobrarlo en todas
      multiplicaría el gasto por la cantidad de filas vigentes y un solo
      intento fallido agotaría el cupo de un saque. Pero esa fila más vieja
      es justo la primera en salir de "vigentes" al vencer, así que sumar
      `intentos` sobre las filas VIGENTES (como hacía la versión anterior)
      reponía el cupo entero con sólo dejar pasar el TTL: medido en
      producción, 5 fallos contra A (que se quedaba con intentos=5) más A
      venciendo le devolvían 5 intentos frescos a B, un código de la MISMA
      dirección que nunca se tipeó.

      El fix suma sobre una VENTANA TEMPORAL en vez de sobre "vigentes":
      todas las filas de la dirección creadas en la última hora, estén
      vigentes, vencidas o ya usadas. Una fila que absorbió intentos sigue
      pesando en la suma después de vencer —hasta que sale de la ventana—,
      así que dejarla vencer ya no repone nada. La ventana es la misma hora
      que `CODIGO_PEDIDOS_HORA` ya usa para el techo de pedidos (RF9): no
      hace falta una segunda constante para lo mismo. `vigentes` (no
      vencidas, no usadas) sigue siendo el conjunto contra el que se compara
      el código y el que recibe el incremento — sólo cambia DE DÓNDE sale la
      suma que se compara contra el techo.
    - "Un canje bueno quema todo lo demás vigente": si sólo se quemara la
      fila que matcheó, un código viejo de un mail anterior seguiría
      sirviendo después de que la persona ya entró.

    No hace falta marcar las filas como "quemadas" sólo por llegar al techo
    de intentos (a diferencia del canje bueno, que sí las quema todas): la
    suma se recalcula en cada llamada sobre la ventana, así que en cuanto el
    total llega al techo, CUALQUIER intento posterior —para cualquiera de los
    códigos vigentes de esa dirección— lo va a encontrar ya al tope y va a
    fallar antes de siquiera comparar el código. Tocar `usado_en` ahí además
    mezclaría dos motivos distintos bajo el mismo campo: "se usó para entrar"
    y "se quedó sin intentos", y ninguna otra parte del código necesita
    distinguirlos.

    `despues_de_marcar`, si se pasa, corre DENTRO del mismo `atomic()` que
    marca las filas como usadas (Hallazgo 2 / C2 de la re-revisión de
    `puertas-de-acceso`). El precheck de `TOMBSTONE_HMAC_KEY` en
    `sessions.py` cierra el caso puntual de esa clave faltante, pero el caso
    GENERAL —cualquier otro fallo al resolver la cuenta después de canjear
    el código— no se cerraba: antes `canjear()` comiteaba `usado_en` y
    recién DESPUÉS la vista intentaba `resolve_account()`, así que un fallo
    ahí (de cualquier tipo) dejaba el código quemado en un login que nunca
    terminó de ocurrir. Metiendo `resolve_account()` y la creación de la
    sesión adentro del `atomic()`, si `despues_de_marcar` levanta lo que
    sea, el rollback deshace también el `usado_en` que se acababa de poner
    y el mismo código sigue sirviendo. El `select_for_update()` de arriba
    sigue sosteniendo la concurrencia (T8): el segundo hilo que compite por
    el mismo código queda bloqueado hasta que el primero termina TODO —no
    sólo marcar la fila—, y los `except IntegrityError` de `accounts.py`
    (creación de cuenta / link de sub concurrente) siguen funcionando porque
    ese `atomic()` interno es un savepoint dentro de éste. No hay ninguna
    llamada de red en este camino (el revoke de Apple vive en
    `deletion.py`), así que extender el lock hasta ahí no expone el login a
    la latencia de un proveedor externo.
    """
    email = normalizar(email)
    ahora = timezone.now()
    ventana_intentos = ahora - timezone.timedelta(hours=1)
    with transaction.atomic():
        vigentes = list(
            CodigoAcceso.objects.select_for_update()
            .filter(email=email, usado_en__isnull=True, expira_en__gt=ahora)
            .order_by("pk")
        )
        if not vigentes:
            raise CodigoInvalido

        intentos_totales = CodigoAcceso.objects.filter(
            email=email, creado_en__gte=ventana_intentos,
        ).aggregate(total=Coalesce(Sum("intentos"), 0))["total"]
        if intentos_totales >= settings.CODIGO_INTENTOS_MAX:
            raise CodigoInvalido

        # El intento se cobra ANTES de comparar: si no, un fallo se puede
        # reintentar sin costo y el techo no frena nada. Ojo: el `save` tiene
        # que quedar DENTRO del atomic pero el `raise` de un mal match tiene
        # que quedar AFUERA — levantar la excepción con el atomic todavía
        # abierto hace rollback de todo el bloque, este incremento incluido,
        # y el techo de intentos nunca se cobra de verdad.
        primera = vigentes[0]
        primera.intentos += 1
        primera.save(update_fields=["intentos"])

        coincidencia = next(
            (fila for fila in vigentes
             if hmac.compare_digest(fila.codigo_hash, hash_token(codigo))),
            None,
        )
        if coincidencia is not None:
            for fila in vigentes:
                fila.usado_en = ahora
            CodigoAcceso.objects.bulk_update(vigentes, ["usado_en"])
            if despues_de_marcar is not None:
                despues_de_marcar(coincidencia)
    if coincidencia is None:
        logger.info(
            "código de acceso rechazado", extra={"intentos": intentos_totales + 1},
        )
        raise CodigoInvalido
    return coincidencia
