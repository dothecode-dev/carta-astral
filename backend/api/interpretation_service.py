"""Orquestación de la interpretación.

Cache en DB (fuente de verdad) + tope global diario + lock de concurrencia,
todo sobre django.core.cache. Construye el cliente Anthropic desde settings y
se lo inyecta a interpret/ (que no toca settings ni la API key).
"""

import logging

import anthropic
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone

from api.exceptions import CapReached, QuotaExceeded
from api.models import Interpretation
from interpret.exceptions import InterpretationError
from interpret.generator import build_interpretation
from interpret.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)

LOCK_TTL = 30

DISCLAIMERS = {
    "es": "Esta interpretación fue generada automáticamente con fines de "
    "entretenimiento; no es un consejo y no tiene valor predictivo demostrado.",
    "en": "This interpretation was generated automatically for entertainment "
    "purposes; it is not advice and has no demonstrated predictive value.",
    "pt": "Esta interpretação foi gerada automaticamente para fins de "
    "entretenimento; não é aconselhamento e não tem valor preditivo comprovado.",
}


def credits_available(installation) -> int:
    used = Interpretation.objects.filter(installation=installation).count()
    return settings.INSTALL_FREE_CREDITS + installation.purchased_credits - used


def _build_client():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=25.0)


def _seconds_until_midnight() -> int:
    now = timezone.now()
    tomorrow = (now + timezone.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((tomorrow - now).total_seconds())


def _existing(chart, lang):
    return Interpretation.objects.filter(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION
    ).first()


def get_or_create_interpretation(chart, lang: str, installation) -> Interpretation:
    hit = _existing(chart, lang)            # §5.1 cache/DB hit: no cuenta
    if hit is not None:
        return hit

    used = Interpretation.objects.filter(installation=installation).count()
    available = settings.INSTALL_FREE_CREDITS + installation.purchased_credits - used
    if available <= 0:                      # §5.2 sin cuota
        raise QuotaExceeded()
    is_free = used < settings.INSTALL_FREE_CREDITS  # tramo cubierto por free-tier

    lock_key = f"interp:lock:{chart.id}:{lang}:{PROMPT_VERSION}"
    if not cache.add(lock_key, "1", timeout=LOCK_TTL):
        hit = _existing(chart, lang)
        if hit is not None:
            return hit
        raise InterpretationError("generación en curso, reintentá en unos segundos")

    try:
        cap = settings.INTERPRETATION_DAILY_CAP
        cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
        if is_free and cache.get(cap_key, 0) >= cap:   # §5.3 cap sólo al free
            logger.warning("interpretation daily cap reached (cap=%s)", cap)
            raise CapReached()

        text = build_interpretation(chart.data, lang, PROMPT_VERSION, _build_client())

        try:
            obj = Interpretation.objects.create(   # §5.5 insertar = cobrar
                chart=chart, lang=lang, prompt_version=PROMPT_VERSION,
                text=text, installation=installation,
            )
        except IntegrityError:
            return _existing(chart, lang)

        if is_free:
            cache.add(cap_key, 0, timeout=_seconds_until_midnight())
            cache.incr(cap_key)
        return obj
    finally:
        cache.delete(lock_key)
