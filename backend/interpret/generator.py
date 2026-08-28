"""Armado del prompt y llamada al LLM.

Aislado de Django y de la API key: recibe el cliente Anthropic inyectado desde
api/ (RNF1/RNF2). No importa django ni api.
"""

import json
import logging

import anthropic

from interpret.exceptions import InterpretationError
from interpret.prompts import (
    MAX_TOKENS,
    MODEL,
    SECCION_TOKENS_POR_PALABRA,
    SYSTEM_PROMPTS,
    SYSTEM_PROMPTS_SECCION,
    TRANSLATE_MAX_TOKENS,
    TRANSLATE_MODEL,
    Seccion,
)

logger = logging.getLogger(__name__)

# Instrucción y nota de degradación en el idioma pedido: si el user message
# va en español, el modelo responde en español aunque el system diga otra cosa.
_INSTRUCTIONS = {
    "es": "Interpretá esta carta natal:",
    "en": "Interpret this natal chart:",
    "pt": "Interprete este mapa astral:",
}

_DEGRADED_NOTES = {
    "es": "\n\nIMPORTANTE: esta carta NO tiene hora de nacimiento conocida. "
    "No interpretes el ascendente ni las casas; limitate a planetas, signos y aspectos.",
    "en": "\n\nIMPORTANT: this chart has NO known birth time. "
    "Do not interpret the ascendant or the houses; stick to planets, signs and aspects.",
    "pt": "\n\nIMPORTANTE: este mapa NÃO tem hora de nascimento conhecida. "
    "Não interprete o ascendente nem as casas; limite-se a planetas, signos e aspectos.",
}


def _user_content(chart_data: dict, lang: str) -> str:
    body = json.dumps(chart_data, ensure_ascii=False)
    content = f"{_INSTRUCTIONS[lang]}\n{body}"
    if not chart_data.get("time_known", True):
        content += _DEGRADED_NOTES[lang]
    return content


def _stream_text(client, model: str, system: list, user_content: str, max_tokens: int) -> str:
    # Streaming interno (no al cliente): el read-timeout pasa a ser por-chunk, lo
    # que evita el corte único de una generación no-streaming larga. La respuesta
    # se devuelve completa igual vía get_final_message().
    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            resp = stream.get_final_message()
    except anthropic.AnthropicError as exc:  # timeout, API, conexión, etc.
        raise InterpretationError(f"error del LLM: {exc}") from exc

    # Observabilidad (HALLAZGO 1 de code review): se loguea SIEMPRE, antes de
    # validar stop_reason, para que el caso que más importa —el techo de
    # max_tokens se quedó corto— quede registrado en vez de perderse en la
    # excepción. Sin esto, la próxima decisión sobre el factor de tokens por
    # palabra (`SECCION_TOKENS_POR_PALABRA`) sale de una estimación y no de
    # datos reales de uso. `getattr` doble porque los fakes de test no
    # siempre traen `usage` (el cliente real de Anthropic sí, siempre).
    output_tokens = getattr(getattr(resp, "usage", None), "output_tokens", None)
    logger.info(
        "llamada al LLM completada: model=%s stop_reason=%s output_tokens=%s max_tokens=%s",
        model, resp.stop_reason, output_tokens, max_tokens,
    )

    if resp.stop_reason not in ("end_turn", "stop_sequence"):
        raise InterpretationError(f"stop_reason inesperado: {resp.stop_reason}")
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        raise InterpretationError("respuesta vacía del LLM")
    return text


def build_interpretation(chart_data: dict, lang: str, prompt_version: str, client) -> str:
    system = [
        {"type": "text", "text": SYSTEM_PROMPTS[lang], "cache_control": {"type": "ephemeral"}}
    ]
    return _stream_text(client, MODEL, system, _user_content(chart_data, lang), MAX_TOKENS)


_TRANSLATE_TARGETS = {
    "es": "español rioplatense (con voseo)",
    "en": "English",
    "pt": "português brasileiro",
}

_TRANSLATE_SYSTEM = (
    "Sos un traductor profesional. Traducí el texto del usuario al {target}. "
    "Es una interpretación astrológica en markdown liviano: conservá los títulos "
    "(#, ##), los párrafos y el tono cálido y directo. Devolvé SOLO la traducción, "
    "sin comentarios ni encabezados extra."
)


def translate_interpretation(text: str, target_lang: str, client) -> str:
    """Traduce una lectura ya generada. Modelo barato: el contenido ya está
    escrito, solo cambia el idioma."""
    system = [{"type": "text", "text": _TRANSLATE_SYSTEM.format(target=_TRANSLATE_TARGETS[target_lang])}]
    return _stream_text(client, TRANSLATE_MODEL, system, text, TRANSLATE_MAX_TOKENS)


_PEDIDO_SECCION = {
    "es": "Escribí la sección «{titulo}» de un informe de carta natal.\n{foco}\nExtensión: unas {palabras} palabras.",
    "en": "Write the «{titulo}» section of a natal chart report.\n{foco}\nLength: about {palabras} words.",
    "pt": "Escreva a seção «{titulo}» de um relatório de mapa natal.\n{foco}\nExtensão: cerca de {palabras} palavras.",
}

_CONTEXTO_PREVIO = {
    "es": "\n\nYA ESCRITO en secciones anteriores (no lo repitas, podés referirte a ello):\n{previo}",
    "en": "\n\nALREADY WRITTEN in earlier sections (don't repeat it, you may refer to it):\n{previo}",
    "pt": "\n\nJÁ ESCRITO em seções anteriores (não repita, pode se referir a isso):\n{previo}",
}


def build_seccion(chart_data: dict, seccion: Seccion, lang: str, previo: str, client) -> str:
    """Genera una sección del informe. `previo` es el resumen de lo ya
    escrito en secciones anteriores: es lo único que impide que, por ejemplo,
    la sección de tensiones repita lo que ya dijo la de la firma. Vacío
    (`""`) para la primera sección.

    Usa _stream_text igual que build_interpretation: las secciones piden
    `SECCION_TOKENS_POR_PALABRA` tokens por palabra objetivo (una sección de
    1000 palabras pide 4000 tokens contra los 1500 de MAX_TOKENS), así que
    el read-timeout por-chunk del streaming es tan o más necesario acá."""
    pedido = _PEDIDO_SECCION[lang].format(
        titulo=seccion.titulo[lang], foco=seccion.foco[lang], palabras=seccion.palabras
    )
    cuerpo = json.dumps(chart_data, ensure_ascii=False)
    content = f"{pedido}\n\n{cuerpo}"
    if not chart_data.get("time_known", True):
        content += _DEGRADED_NOTES[lang]
    if previo:
        content += _CONTEXTO_PREVIO[lang].format(previo=previo)

    # SYSTEM_PROMPTS_SECCION, no SYSTEM_PROMPTS: éste no fija un largo (lo fija
    # el pedido, que varía por sección) y aclara que es una sección de un
    # informe más largo, no una pieza autónoma. SYSTEM_PROMPTS sigue siendo de
    # build_interpretation, la lectura corta que ya está en producción.
    # cache_control queda diferido: es optimización de costo, no correctitud
    # (ver ítem de cierre del plan que mide el costo real de un informe).
    system = [{"type": "text", "text": SYSTEM_PROMPTS_SECCION[lang]}]
    # Holgura sobre el objetivo: un tope justo corta la sección a la mitad
    # (HALLAZGO 1 de code review — ver la justificación del factor en
    # interpret/prompts.py, junto a SECCION_TOKENS_POR_PALABRA).
    return _stream_text(client, MODEL, system, content, seccion.palabras * SECCION_TOKENS_POR_PALABRA)
