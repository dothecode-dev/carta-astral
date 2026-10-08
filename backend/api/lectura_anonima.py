"""La lectura breve sin cuenta (spec docs/2026-10-08-spec-lectura-anonima.md).

Los datos de nacimiento NO se guardan: el hilo los recibe en memoria. En la
caché queda `{estado, lang, pedido, iniciado, fecha_cupo[, texto]}` bajo el
hash del token, 15 minutos como máximo. La entrega es en dos tiempos (spec §11):
el GET que devuelve `lista` NO la borra —si la respuesta se pierde, el navegador
la vuelve a pedir—; la borra el acuse (`acusar`, el DELETE) o el vencimiento.
Después vive sólo en el navegador. Una marca sin datos personales recuerda
24 h que ese token ya usó su lectura gratis.

Orden de los chequeos de `pedir`, y por qué (spec §11, RF13 v3):
  mantenimiento → ya usado → en curso → slot de concurrencia → cupo → IP.
El techo por IP se consume último: ni un «ocupado» (que la web reintenta
sola) ni un «sin cupo» lo gastan. Si la IP rechaza, se devuelve el cupo
recién reservado. Reintentar la lectura fallida (o caída) del mismo token y
pedido no consulta la IP.

El `pedido` es un id que la web genera por cada vez que se aprieta «leer» (no
es un dato personal). Con el mismo token, mientras una lectura se escribe, sólo
el MISMO pedido recibe 202: otro pedido es otra carta —volvió atrás, corrigió
la hora, o es otra persona en el mismo teléfono— y recibe 409. Sin esto la web
recibía la lectura de la carta A y la mostraba y guardaba como la de B.
"""
import datetime as dt
import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import connections

from api import cupo_diario, informe_service, mantenimiento
from api.identity import hash_token
from api.interpretation_service import DISCLAIMERS, _build_client

logger = logging.getLogger(__name__)

TTL_ENTRADA = 15 * 60
TTL_MARCA = 24 * 60 * 60
TTL_SLOT = 90
TTL_LOCK = 30
CAIDA_SEGUNDOS = 90
# Mientras el hilo escribe, cada LATIDO_SEGUNDOS renueva su slot (TTL_SLOT) y
# anota `ultimo_latido` en la entrada. Una lectura tarda más que TTL_SLOT y
# que CAIDA_SEGUNDOS: sin latido el slot vencía a mitad de escritura y el GET
# daba por caída una lectura viva (spec §11, RF12/RF15 v3).
LATIDO_SEGUNDOS = 30
# Tope de vida de una generación: pasado esto el latido deja de renovar, así
# que un stream que no termina nunca queda caído CAIDA_SEGUNDOS después y su
# cupo vuelve (una vez, por `_devolver_una_vez`). Una lectura normal tarda
# bastante menos.
LECTURA_MAX_SEGUNDOS = 300


def _ahora() -> float:
    return time.time()


class Mantenimiento(Exception):
    pass


class Usado(Exception):
    pass


class Ocupado(Exception):
    pass


class PorIP(Exception):
    pass


class SinCupo(Exception):
    pass


@dataclass(frozen=True)
class Pedido:
    token: str
    estado: str


def _clave(h: str) -> str:
    return f"lectura_anonima:{h}"


def _marca(h: str) -> str:
    return f"lectura_anonima:usado:{h}"


def _lock(h: str) -> str:
    return f"lectura_anonima:lock:{h}"


def _slot(i: int) -> str:
    return f"lectura_anonima:slot:{i}"


def _devuelto(h: str, iniciado: float) -> str:
    return f"lectura_anonima:devuelto:{h}:{iniciado}"


def _caida(entrada: dict) -> bool:
    """`generando` sin latido hace más de CAIDA_SEGUNDOS: el hilo murió."""
    if entrada["estado"] != "generando":
        return False
    return _ahora() - entrada.get("ultimo_latido", entrada["iniciado"]) > CAIDA_SEGUNDOS


def _devolver_una_vez(h: str, iniciado: float, fecha: dt.date) -> None:
    """Devuelve el lugar de ESA generación una sola vez, la pida el hilo que
    falló o el GET que la dio por caída (compare-and-swap con `cache.add`)."""
    if cache.add(_devuelto(h, iniciado), 1, timeout=TTL_ENTRADA):
        cupo_diario.devolver(cupo_diario.ANONIMO, fecha)


def _tomar_slot(h: str) -> int | None:
    for i in range(settings.LECTURA_ANONIMA_CONCURRENCIA):
        if cache.add(_slot(i), h, timeout=TTL_SLOT):
            return i
    return None


def _soltar_slot(slot: int, h: str) -> None:
    """Suelta el slot sólo si sigue siendo de esta generación: tras más de
    TTL_SLOT segundos pudo vencer y estar en manos de otro pedido."""
    if cache.get(_slot(slot)) == h:
        cache.delete(_slot(slot))


def _en_curso(entrada: dict | None, pedido: str) -> bool:
    """True si ya se está escribiendo ESTE pedido (202 sin lanzar nada).
    Si se está escribiendo otro, es otra carta: `Usado`."""
    if entrada is None or entrada["estado"] != "generando" or _caida(entrada):
        return False
    if entrada.get("pedido") != pedido:
        raise Usado()
    return True


def _es_reintento(entrada: dict | None, pedido: str) -> bool:
    """La entrada es una lectura de ESTE pedido que falló o se cayó."""
    return (
        entrada is not None and entrada.get("pedido") == pedido
        and (entrada["estado"] == "fallida" or _caida(entrada))
    )


def _lista_propia(h: str, pedido: str) -> bool:
    """True si la lectura de ESTE pedido está escrita y sin acusar: con la marca
    puesta, un POST del mismo pedido la recibe (202 `lista`) en vez de 409."""
    entrada = cache.get(_clave(h))
    return entrada is not None and entrada["estado"] == "lista" and entrada.get("pedido") == pedido


def pedir(chart_data: dict, lang: str, trato: str, token: str | None,
          permitir: Callable[[], bool], *, pedido: str) -> Pedido:
    if mantenimiento.activo():
        raise Mantenimiento()
    token = token or secrets.token_urlsafe(32)
    h = hash_token(token)
    if cache.get(_marca(h)) is not None:
        if _lista_propia(h, pedido):
            return Pedido(token, "lista")
        raise Usado()
    if _en_curso(cache.get(_clave(h)), pedido):
        return Pedido(token, "generando")
    if not cache.add(_lock(h), pedido, timeout=TTL_LOCK):
        # Otro POST del mismo token está adentro ahora mismo. Si es el mismo
        # pedido (un reintento), espera su lectura; si es otro, es otra carta.
        if cache.get(_lock(h)) != pedido:
            raise Usado()
        return Pedido(token, "generando")
    try:
        # Se vuelve a leer ya con el lock: entre la lectura de arriba y el lock
        # otro pedido del mismo token pudo haber escrito la entrada o la marca.
        if cache.get(_marca(h)) is not None:
            if _lista_propia(h, pedido):
                return Pedido(token, "lista")
            raise Usado()
        entrada = cache.get(_clave(h))
        if _en_curso(entrada, pedido):
            return Pedido(token, "generando")
        slot = _tomar_slot(h)
        if slot is None:
            logger.info("lectura anónima: sin slot libre")
            raise Ocupado()
        fecha = None
        try:
            if entrada is not None and _caida(entrada):
                # La generación anterior se dio por caída: su lugar vuelve una
                # sola vez antes de reservar el nuevo.
                _devolver_una_vez(
                    h, entrada["iniciado"], dt.date.fromisoformat(entrada["fecha_cupo"])
                )
            fecha = cupo_diario.reservar(cupo_diario.ANONIMO, settings.INTERPRETATION_ANON_DAILY_CAP)
            if fecha is None:
                logger.warning(
                    "lectura anónima: cupo diario agotado (cap=%s)",
                    settings.INTERPRETATION_ANON_DAILY_CAP,
                )
                raise SinCupo()
            # La IP va última: un «ocupado» o un «sin cupo» no la gastan, y
            # reintentar la fallida (o caída) del MISMO pedido tampoco —es la
            # misma lectura que ya la pagó—. Si rechaza, el `except` devuelve
            # el cupo recién reservado y suelta el slot.
            if not _es_reintento(entrada, pedido) and not permitir():
                raise PorIP()
            iniciado = _ahora()
            cache.set(_clave(h), {
                "estado": "generando", "lang": lang, "pedido": pedido,
                "iniciado": iniciado, "fecha_cupo": fecha.isoformat(),
            }, TTL_ENTRADA)
            logger.info("lectura anónima pedida (lang=%s)", lang)
            _arrancar_en_hilo(h, chart_data, lang, trato, slot, fecha, iniciado, pedido)
        except BaseException:
            # Cualquier salida antes de que el hilo tenga el slot y el lugar
            # (los rechazos esperados incluidos) los suelta; si el hilo ya
            # arrancó, `generar` es quien los suelta.
            _soltar_slot(slot, h)
            if fecha is not None:
                cupo_diario.devolver(cupo_diario.ANONIMO, fecha)
            raise
    finally:
        cache.delete(_lock(h))
    return Pedido(token, "generando")


def _latir(h: str, slot: int, pedido: str, iniciado: float) -> None:
    """Renueva el slot (sólo si sigue siendo nuestro, como `_soltar_slot`) y
    anota el latido en la entrada sólo si sigue siendo ESTA generación: mismo
    pedido, mismo `iniciado` y todavía `generando`. Pasados
    LECTURA_MAX_SEGUNDOS desde el inicio no renueva nada: deja caer la
    generación."""
    if _ahora() - iniciado > LECTURA_MAX_SEGUNDOS:
        logger.warning("lectura anónima: pasó el tope de %ss, el latido no renueva", LECTURA_MAX_SEGUNDOS)
        return
    if cache.get(_slot(slot)) == h:
        cache.touch(_slot(slot), TTL_SLOT)
    entrada = cache.get(_clave(h))
    if (
        entrada is not None and entrada["estado"] == "generando"
        and entrada.get("pedido") == pedido and entrada.get("iniciado") == iniciado
    ):
        cache.set(_clave(h), {**entrada, "ultimo_latido": _ahora()}, TTL_ENTRADA)


@contextmanager
def _latido(h: str, slot: int, pedido: str, iniciado: float) -> Iterator[None]:
    """Late en otro hilo mientras dura el bloque. Al salir lo detiene y lo
    ESPERA: un latido en vuelo leyendo `generando` no puede escribir después
    de que `generar` escribió `lista` o `fallida`."""
    parar = threading.Event()

    def correr() -> None:
        try:
            while not parar.wait(LATIDO_SEGUNDOS):
                try:
                    _latir(h, slot, pedido, iniciado)
                except Exception:
                    logger.exception("lectura anónima: el latido falló")
        finally:
            connections.close_all()

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    try:
        yield
    finally:
        parar.set()
        hilo.join()


def generar(h: str, chart_data: dict, lang: str, trato: str, slot: int,
            fecha: dt.date, iniciado: float, pedido: str) -> None:
    try:
        with _latido(h, slot, pedido, iniciado):
            texto = informe_service.escribir_breve(chart_data, lang, trato, _build_client())
    except Exception:
        logger.exception("lectura anónima fallida (lang=%s)", lang)
        _devolver_una_vez(h, iniciado, fecha)
        cache.set(_clave(h), {"estado": "fallida", "lang": lang, "pedido": pedido}, TTL_ENTRADA)
    else:
        # La marca va ANTES que la lista: si no, un POST que cae entre las dos
        # escrituras no ve marca ni `generando` y lanza otra lectura gratis.
        cache.set(_marca(h), 1, TTL_MARCA)
        cache.set(_clave(h), {"estado": "lista", "lang": lang, "pedido": pedido, "texto": texto}, TTL_ENTRADA)
        logger.info("lectura anónima lista (lang=%s)", lang)
    finally:
        _soltar_slot(slot, h)


def _arrancar_en_hilo(*args) -> None:
    def _en_hilo():
        try:
            generar(*args)
        except Exception:
            logger.exception("el hilo de la lectura anónima murió sin control")
        finally:
            connections.close_all()

    threading.Thread(target=_en_hilo, daemon=True).start()


def estado(token: str) -> dict | None:
    h = hash_token(token)
    entrada = cache.get(_clave(h))
    if entrada is None:
        return None
    if _caida(entrada):
        _devolver_una_vez(h, entrada["iniciado"], dt.date.fromisoformat(entrada["fecha_cupo"]))
        cache.set(_clave(h), {
            "estado": "fallida", "lang": entrada["lang"], "pedido": entrada.get("pedido"),
        }, TTL_ENTRADA)
        return {"estado": "fallida", "pedido": entrada.get("pedido")}
    if entrada["estado"] == "lista":
        return {
            "estado": "lista", "texto": entrada["texto"], "lang": entrada["lang"],
            "disclaimer": DISCLAIMERS[entrada["lang"]], "pedido": entrada.get("pedido"),
        }
    return {"estado": entrada["estado"], "pedido": entrada.get("pedido")}


def acusar(token: str, pedido: str) -> bool:
    """El acuse de recibo de la web: borra la lectura `lista` de ESE pedido.
    False si no hay nada que borrar —ya acusada, vencida, de otro pedido o
    todavía escribiéndose (borrar un `generando` perdería la detección de
    caída y, con ella, la devolución del cupo)—."""
    h = hash_token(token)
    if not _lista_propia(h, pedido):
        return False
    cache.delete(_clave(h))
    return True
