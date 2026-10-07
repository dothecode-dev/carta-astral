"""Cómo quiere la persona que le hablen (spec docs/2026-10-07-spec-trato-lector.md).

Vive en `interpret/` porque la instrucción al modelo sale de acá; `api` lo
importa para validar. Vacío = no eligió, y se trata igual que "neutro".
"""

TRATOS = ("femenino", "masculino", "neutro")

_INSTRUCCIONES = {
    "es": {
        "femenino": "Dirigite a la persona en femenino (por ejemplo «vos misma», «segura») en todo "
                    "adjetivo, participio y pronombre que se refiera a ella, incluidos ejemplos y "
                    "preguntas, de forma consistente en todo el texto. Esto vale sólo para quien "
                    "lee; a terceros (pareja, madre, padre) nombralos como corresponda.",
        "masculino": "Dirigite a la persona en masculino (por ejemplo «vos mismo», «seguro») en todo "
                     "adjetivo, participio y pronombre que se refiera a él, incluidos ejemplos y "
                     "preguntas, de forma consistente en todo el texto. Esto vale sólo para quien "
                     "lee; a terceros (pareja, madre, padre) nombralos como corresponda.",
        "neutro": "No marques el género de la persona: ningún adjetivo ni participio referido a ella "
                  "puede llevar terminación de género. Reformulá: usá sustantivos («tenés seguridad», "
                  "«tu sensibilidad»), verbos («confiás en vos») o adjetivos que no cambian («sos "
                  "sensible», «sos capaz»). No abuses de «sos una persona…». Nunca uses barras, «x», "
                  "«@» ni «e» como terminación neutra. Esto vale sólo para quien lee; a terceros "
                  "nombralos como corresponda.",
    },
    "pt": {
        "femenino": "Dirija-se à pessoa no feminino (por exemplo «você mesma», «segura») em todo "
                    "adjetivo, particípio e pronome que se refira a ela, incluindo exemplos e "
                    "perguntas, de forma consistente em todo o texto. Isso vale só para quem lê; "
                    "terceiros (parceiro, mãe, pai) devem ser nomeados normalmente.",
        "masculino": "Dirija-se à pessoa no masculino (por exemplo «você mesmo», «seguro») em todo "
                     "adjetivo, particípio e pronome que se refira a ele, incluindo exemplos e "
                     "perguntas, de forma consistente em todo o texto. Isso vale só para quem lê; "
                     "terceiros (parceiro, mãe, pai) devem ser nomeados normalmente.",
        "neutro": "Não marque o gênero da pessoa: nenhum adjetivo ou particípio referido a ela pode "
                  "ter terminação de gênero. Reformule: use substantivos («você tem segurança», "
                  "«sua sensibilidade»), verbos («você confia em si») ou adjetivos que não mudam "
                  "(«você é sensível», «você é capaz»). Não abuse de «você é uma pessoa…». Nunca use "
                  "barras, «x», «@» nem «e» como terminação neutra. Isso vale só para quem lê; "
                  "terceiros devem ser nomeados normalmente.",
    },
}


def instruccion(trato: str, lang: str) -> str:
    """La instrucción de trato para el modelo; "" en inglés (no marca género)."""
    por_idioma = _INSTRUCCIONES.get(lang)
    if por_idioma is None:
        return ""
    return por_idioma.get(trato) or por_idioma["neutro"]
