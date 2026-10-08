"""La lectura breve sin cuenta (spec docs/2026-10-08-spec-lectura-anonima.md).

Los datos de nacimiento NO se guardan: el hilo los recibe en memoria. En la
caché queda `{estado, lang, iniciado, fecha_cupo[, texto]}` bajo el hash del
token, 15 minutos como máximo, y el GET que entrega la lectura la borra.
Después vive sólo en el navegador. Una marca sin datos personales recuerda
24 h que ese token ya usó su lectura gratis.

Orden de los chequeos de `pedir`, y por qué:
  mantenimiento → ya usado → en curso → slot de concurrencia → IP → cupo.
El slot va antes de la IP para que un «ocupado» (que la web reintenta sola)
no gaste el techo por IP; la IP va antes del cupo para no reservar un lugar
que después hay que devolver.
"""
import datetime as dt
import logging
import secrets
import threading
import time
from collections.abc import Callable
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
    return entrada["estado"] == "generando" and time.time() - entrada["iniciado"] > CAIDA_SEGUNDOS


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


def pedir(chart_data: dict, lang: str, trato: str, token: str | None,
          permitir: Callable[[], bool]) -> Pedido:
    if mantenimiento.activo():
        raise Mantenimiento()
    token = token or secrets.token_urlsafe(32)
    h = hash_token(token)
    if cache.get(_marca(h)) is not None:
        raise Usado()
    entrada = cache.get(_clave(h))
    if entrada is not None and entrada["estado"] == "generando" and not _caida(entrada):
        return Pedido(token, "generando")
    if not cache.add(_lock(h), 1, timeout=TTL_LOCK):
        return Pedido(token, "generando")
    try:
        slot = _tomar_slot(h)
        if slot is None:
            logger.info("lectura anónima: sin slot libre")
            raise Ocupado()
        if not permitir():
            cache.delete(_slot(slot))
            raise PorIP()
        fecha = cupo_diario.reservar(cupo_diario.ANONIMO, settings.INTERPRETATION_ANON_DAILY_CAP)
        if fecha is None:
            cache.delete(_slot(slot))
            logger.warning(
                "lectura anónima: cupo diario agotado (cap=%s)",
                settings.INTERPRETATION_ANON_DAILY_CAP,
            )
            raise SinCupo()
        iniciado = time.time()
        cache.set(_clave(h), {
            "estado": "generando", "lang": lang, "iniciado": iniciado,
            "fecha_cupo": fecha.isoformat(),
        }, TTL_ENTRADA)
        logger.info("lectura anónima pedida (lang=%s)", lang)
        _arrancar_en_hilo(h, chart_data, lang, trato, slot, fecha, iniciado)
    finally:
        cache.delete(_lock(h))
    return Pedido(token, "generando")


def generar(h: str, chart_data: dict, lang: str, trato: str, slot: int,
            fecha: dt.date, iniciado: float) -> None:
    try:
        texto = informe_service.escribir_breve(chart_data, lang, trato, _build_client())
    except Exception:
        logger.exception("lectura anónima fallida (lang=%s)", lang)
        _devolver_una_vez(h, iniciado, fecha)
        cache.set(_clave(h), {"estado": "fallida", "lang": lang}, TTL_ENTRADA)
    else:
        cache.set(_clave(h), {"estado": "lista", "lang": lang, "texto": texto}, TTL_ENTRADA)
        cache.set(_marca(h), 1, TTL_MARCA)
        logger.info("lectura anónima lista (lang=%s)", lang)
    finally:
        cache.delete(_slot(slot))


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
        cache.set(_clave(h), {"estado": "fallida", "lang": entrada["lang"]}, TTL_ENTRADA)
        return {"estado": "fallida"}
    if entrada["estado"] == "lista":
        cache.delete(_clave(h))
        return {
            "estado": "lista", "texto": entrada["texto"], "lang": entrada["lang"],
            "disclaimer": DISCLAIMERS[entrada["lang"]],
        }
    return {"estado": entrada["estado"]}
