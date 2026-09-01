"""El techo de tokens de la lectura breve tiene que cubrir lo que su prompt pide.

Este test existe por un incidente de producción del 31-08-2026. El deploy de los
dos tiers estrenó `claude-sonnet-5` para la lectura breve manteniendo el
`MAX_TOKENS = 1500` del producto anterior, mientras el system pide "400 a 700
palabras". En español hacen falta ~4 tokens por palabra —el mismo factor que el
informe por secciones ya usa en `SECCION_TOKENS_POR_PALABRA`—, así que ni el
MÍNIMO del rango entraba (400 x 4 = 1600 > 1500): el modelo llegaba al límite a
mitad de frase y `build_interpretation` abortaba con "stop_reason inesperado:
max_tokens". La lectura breve falló el 100% de las veces durante 25 horas, y dos
usuarios reales se quedaron sin su lectura y con el crédito descontado.

El bug fue que el prompt decía un número y el techo otro, sin nada que los atara.
Esto los ata.
"""

import re

import pytest

from interpret.prompts import (
    MAX_TOKENS,
    SECCION_TOKENS_POR_PALABRA,
    SYSTEM_PROMPTS,
)

# "400 a 700 palabras" (es), "400 a 700 palavras" (pt), "400-700 word" (en).
# Los tres idiomas lo escriben distinto, así que el patrón acepta las tres formas.
_RANGO = re.compile(r"(\d+)\s*(?:a|to|-|–)\s*(\d+)\s+(?:palabras|palavras|words?)")


def _maximo_de_palabras(prompt: str) -> int:
    encontrado = _RANGO.search(prompt)
    assert encontrado is not None, (
        "el system prompt dejó de declarar un rango de palabras: si cambió la forma "
        "de pedirlo, hay que actualizar este test, no borrarlo — es lo único que ata "
        "el largo pedido con el techo de tokens"
    )
    return int(encontrado.group(2))


@pytest.mark.parametrize("lang", sorted(SYSTEM_PROMPTS))
def test_el_techo_cubre_el_maximo_de_palabras_que_pide_cada_idioma(lang):
    maximo = _maximo_de_palabras(SYSTEM_PROMPTS[lang])

    assert MAX_TOKENS >= maximo * SECCION_TOKENS_POR_PALABRA, (
        f"el system de {lang} pide hasta {maximo} palabras, que a "
        f"{SECCION_TOKENS_POR_PALABRA} tokens por palabra son "
        f"{maximo * SECCION_TOKENS_POR_PALABRA} tokens, pero el techo es {MAX_TOKENS}: "
        "el modelo se va a cortar por max_tokens y la generación va a abortar"
    )


def test_los_tres_idiomas_piden_el_mismo_largo():
    """Si un idioma pidiera más que otro, el techo tendría que cubrir al mayor."""
    maximos = {lang: _maximo_de_palabras(p) for lang, p in SYSTEM_PROMPTS.items()}

    assert len(set(maximos.values())) == 1, maximos
