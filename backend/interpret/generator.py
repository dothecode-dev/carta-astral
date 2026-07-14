"""Armado del prompt y llamada al LLM.

Aislado de Django y de la API key: recibe el cliente Anthropic inyectado desde
api/ (RNF1/RNF2). No importa django ni api.
"""

import json

import anthropic

from interpret.exceptions import InterpretationError
from interpret.prompts import MAX_TOKENS, MODEL, SYSTEM_PROMPTS

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


def build_interpretation(chart_data: dict, lang: str, prompt_version: str, client) -> str:
    system = SYSTEM_PROMPTS[lang]
    # Streaming interno (no al cliente): el read-timeout pasa a ser por-chunk, lo
    # que evita el corte único de una generación no-streaming larga. La respuesta
    # se devuelve completa igual vía get_final_message().
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _user_content(chart_data, lang)}],
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
