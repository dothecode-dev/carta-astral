"""Cómo quiere la persona que le hablen (spec docs/2026-10-07-spec-trato-lector.md).

Vive en `interpret/` porque la instrucción al modelo sale de acá; `api` lo
importa para validar. Vacío = no eligió, y se trata igual que "neutro".
"""

TRATOS = ("femenino", "masculino", "neutro")

_INSTRUCCIONES = {
    "es": {
        "femenino": "Dirigite a la persona en femenino (por ejemplo «vos misma», «segura»), "
                    "de forma consistente en todo el texto.",
        "masculino": "Dirigite a la persona en masculino (por ejemplo «vos mismo», «seguro»), "
                     "de forma consistente en todo el texto.",
        "neutro": "No marques el género de la persona en ningún adjetivo ni participio que se "
                  "refiera a ella: reformulá la frase («te da seguridad» en vez de «sos seguro/a»). "
                  "No uses barras («o/a»), ni «x», «@» o «e» como terminación neutra.",
    },
    "pt": {
        "femenino": "Dirija-se à pessoa no feminino (por exemplo «você mesma», «segura»), "
                    "de forma consistente em todo o texto.",
        "masculino": "Dirija-se à pessoa no masculino (por exemplo «você mesmo», «seguro»), "
                     "de forma consistente em todo o texto.",
        "neutro": "Não marque o gênero da pessoa em nenhum adjetivo ou particípio que se refira a "
                  "ela: reformule a frase («isso te dá segurança» em vez de «você é seguro/a»). "
                  "Não use barras («o/a»), nem «x», «@» ou «e» como terminação neutra.",
    },
}


def instruccion(trato: str, lang: str) -> str:
    """La instrucción de trato para el modelo; "" en inglés (no marca género)."""
    por_idioma = _INSTRUCCIONES.get(lang)
    if por_idioma is None:
        return ""
    return por_idioma.get(trato) or por_idioma["neutro"]
