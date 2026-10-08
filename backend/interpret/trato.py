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
        "neutro": "No marques el género de quien lee: ningún adjetivo, participio ni pronombre referido a esa persona puede terminar en -o/-a. Eso incluye «vos mismo» y «vos misma»: usá «vos», «a vos», «tu propia…» o «por tu cuenta» («te sorprende incluso a vos», «versiones de vos», «que levantás por tu cuenta»). Lo mismo con «dispuesto», «solo», «atrapado», «sorprendido», «seguro», «cansado» y similares: reformulá con verbos («estás en condiciones de», «te sorprende», «te sentís sin salida»), sustantivos («tenés seguridad», «tu sensibilidad») o adjetivos que no cambian («sos sensible», «sos capaz»). No abuses de «sos una persona…». Nunca uses barras, «x», «@» ni «e» como terminación neutra. Antes de terminar, revisá que no quede ninguna forma con género referida a quien lee. Esto vale sólo para quien lee; a terceros nombralos como corresponda.",
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
        "neutro": "Não marque o gênero de quem lê: nenhum adjetivo, particípio ou pronome referido a essa pessoa pode terminar em -o/-a. Isso inclui «você mesmo» e «você mesma»: use «você», «a si», «sua própria…» ou «por conta própria» («surpreende até você», «versões de você», «que você ergue por conta própria»). O mesmo vale para «disposto», «sozinho», «preso», «surpreso», «seguro», «cansado» e similares: reformule com verbos («você está em condições de», «isso te surpreende», «você se sente sem saída»), substantivos («você tem segurança», «sua sensibilidade») ou adjetivos que não mudam («você é sensível», «você é capaz»). Não abuse de «você é uma pessoa…». Nunca use barras, «x», «@» nem «e» como terminação neutra. Antes de terminar, revise que não reste nenhuma forma com gênero referida a quem lê. Isso vale só para quem lê; terceiros devem ser nomeados normalmente.",
    },
}


def instruccion(trato: str, lang: str) -> str:
    """La instrucción de trato para el modelo; "" en inglés (no marca género)."""
    por_idioma = _INSTRUCCIONES.get(lang)
    if por_idioma is None:
        return ""
    return por_idioma.get(trato) or por_idioma["neutro"]
