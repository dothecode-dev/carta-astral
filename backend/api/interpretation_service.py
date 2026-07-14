"""Orquestación de la interpretación.

Cache en DB (fuente de verdad) + tope global diario + lock de concurrencia,
todo sobre django.core.cache. Construye el cliente Anthropic desde settings y
se lo inyecta a interpret/ (que no toca settings ni la API key).
"""

import hashlib
import json
import logging

import anthropic
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from api import ledger
from api.exceptions import CapReached, QuotaExceeded
from api.models import Interpretation
from interpret.exceptions import InterpretationError
from interpret.generator import build_interpretation, translate_interpretation
from interpret.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)

LOCK_TTL = 30

DISCLAIMERS = {
    "es": "Esta interpretación fue generada con inteligencia artificial con fines "
    "de entretenimiento; no es consejo médico, legal ni financiero y no tiene "
    "valor predictivo demostrado.",
    "en": "This interpretation was generated with artificial intelligence for "
    "entertainment purposes; it is not medical, legal or financial advice and "
    "has no demonstrated predictive value.",
    "pt": "Esta interpretação foi gerada com inteligência artificial para fins "
    "de entretenimento; não é conselho médico, legal ou financeiro e não tem "
    "valor preditivo comprovado.",
}


def credits_available(account) -> int:
    return ledger.credits_available(account)


def _build_client():
    if not settings.ANTHROPIC_API_KEY:
        # Sin key el SDK lanza TypeError (500 crudo); mejor un 503 prolijo.
        raise InterpretationError("ANTHROPIC_API_KEY no configurada")
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


def interpretation_langs(chart) -> list[str]:
    """Idiomas en los que esta carta ya tiene lectura (prompt actual)."""
    return list(
        Interpretation.objects.filter(chart=chart, prompt_version=PROMPT_VERSION)
        .values_list("lang", flat=True)
    )


def content_key(chart_data: dict, lang: str, prompt_version: str) -> str:
    """Hash canónico del input del LLM. Dos cartas con el mismo JSON astrológico
    (mismo instante UTC, lugar, house system, engine) comparten lectura."""
    canonical = json.dumps(chart_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{prompt_version}:{lang}:{canonical}".encode()).hexdigest()


def get_or_create_interpretation(chart, lang: str, account) -> Interpretation:
    hit = _existing(chart, lang)
    if hit is not None:
        return hit

    # El crédito se cobra UNA vez por carta: la primera lectura, en el idioma
    # que sea. Los demás idiomas son traducciones de esa lectura, gratis.
    sibling = (
        Interpretation.objects.filter(chart=chart, prompt_version=PROMPT_VERSION)
        .exclude(lang=lang)
        .first()
    )
    will_charge = sibling is None

    if will_charge and ledger.credits_available(account) <= 0:
        raise QuotaExceeded()

    lock_key = f"interp:lock:{chart.id}:{lang}:{PROMPT_VERSION}"
    if not cache.add(lock_key, "1", timeout=LOCK_TTL):
        hit = _existing(chart, lang)
        if hit is not None:
            return hit
        raise InterpretationError("generación en curso, reintentá en unos segundos")

    try:
        key = content_key(chart.data, lang, PROMPT_VERSION)
        # Dedup entre cartas: mismo input del LLM → se reutiliza el texto sin
        # llamar a la API. El crédito de la carta se cobra igual; solo el costo
        # LLM y el cap aplican a generaciones reales.
        donor = Interpretation.objects.filter(content_key=key).first()
        llm_generated = False
        if donor is not None:
            text = donor.text
        elif sibling is not None:
            # Traducción con modelo barato; fuera del cap (no es generación).
            text = translate_interpretation(sibling.text, lang, _build_client())
        else:
            # Determine lot BEFORE charging to apply the cap only to free generations.
            will_be_free = account.free_balance > 0
            cap = settings.INTERPRETATION_DAILY_CAP
            cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
            if will_be_free and cache.get(cap_key, 0) >= cap:
                logger.warning("interpretation daily cap reached (cap=%s)", cap)
                raise CapReached()

            text = build_interpretation(chart.data, lang, PROMPT_VERSION, _build_client())
            llm_generated = True

        def _factory():
            try:
                with transaction.atomic():
                    return Interpretation.objects.create(
                        chart=chart, lang=lang, prompt_version=PROMPT_VERSION,
                        text=text, account=account, content_key=key,
                    )
            except IntegrityError:
                return _existing(chart, lang)

        if not will_charge:
            return _factory()

        obj, lot = ledger.charge(account, _factory)
        if lot == "free" and llm_generated:
            cache.add(cap_key, 0, timeout=_seconds_until_midnight())
            cache.incr(cap_key)
        return obj
    finally:
        cache.delete(lock_key)
