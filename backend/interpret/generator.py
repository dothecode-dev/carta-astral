"""Armado del prompt y llamada al LLM.

Aislado de Django y de la API key: recibe el cliente Anthropic inyectado desde
api/ (RNF1/RNF2). No importa django ni api.
"""

import json

import anthropic

from interpret.exceptions import InterpretationError
from interpret.prompts import (
    MAX_TOKENS,
    MODEL,
    SYSTEM_PROMPTS,
    TRANSLATE_MAX_TOKENS,
    TRANSLATE_MODEL,
)

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
