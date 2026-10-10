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
        "neutro": "Não marque o gênero de quem lê: nenhum adjetivo, particípio ou pronome referido a essa pessoa pode terminar em -o/-a. Isso inclui «você mesmo» e «você mesma»: use «você», «a si», «sua própria…» ou «por conta própria» («surpreende até você», «versões de você», «que você ergue por conta própria»). Também os pronomes oblíquos: nunca use «o» nem «a» para se referir a quem lê («o empurra», «a torna», «o faz sentir»); use «te» ou «lhe», ou reformule com «você» como sujeito («Áries te empurra», «isso faz você sentir»). E nada de «consigo mesmo» ou «consigo mesma»: use «consigo» ou «com você». O mesmo vale para «disposto», «sozinho», «preso», «surpreso», «seguro», «cansado» e similares: reformule com verbos («você está em condições de», «isso te surpreende», «você se sente sem saída»), substantivos («você tem segurança», «sua sensibilidade») ou adjetivos que não mudam («você é sensível», «você é capaz»). Não abuse de «você é uma pessoa…». Nunca use barras, «x», «@» nem «e» como terminação neutra. Antes de terminar, revise que não reste nenhuma forma com gênero referida a quem lê. Isso vale só para quem lê; terceiros devem ser nomeados normalmente.",
    },
}


def instruccion(trato: str, lang: str) -> str:
    """La instrucción de trato para el modelo; "" en inglés (no marca género)."""
    por_idioma = _INSTRUCCIONES.get(lang)
    if por_idioma is None:
        return ""
    return por_idioma.get(trato) or por_idioma["neutro"]


# Cómo se nombra a cada persona del vínculo en cada idioma: lo que el modelo
# escribe y donde la web pone el alias (RF22).
_NOMBRE_PERSONA = {"es": "Persona {}", "en": "Person {}", "pt": "Pessoa {}"}


def nombre_persona(letra: str, lang: str) -> str:
    return _NOMBRE_PERSONA[lang].format(letra)


# El género de alguien de quien el texto HABLA, en tercera persona: las dos
# personas del vínculo (decisión del 10-10-2026). Medido en staging el 10-10:
# con una línea («redactá de forma neutra») el modelo escribió «se percibe a sí
# mismo», «sentirse seguro», «con solo mirarlo» y «como progenitor». Por eso
# la neutra nombra esas formas, igual que la del lector.
_INSTRUCCIONES_PERSONA = {
    "es": {
        "femenino": "{p} es mujer: todo adjetivo, participio y pronombre referido a {p} va en "
                    "femenino («a sí misma», «segura», «ella», «mirarla»), de forma consistente "
                    "en todo el texto.",
        "masculino": "{p} es varón: todo adjetivo, participio y pronombre referido a {p} va en "
                     "masculino («a sí mismo», «seguro», «él», «mirarlo»), de forma consistente "
                     "en todo el texto.",
        "neutro": "No se sabe el género de {p} y no hay que marcarlo: ningún adjetivo, participio ni pronombre referido a {p} puede terminar en -o/-a. Nada de «a sí mismo» ni «a sí misma»: usá «se percibe», «por su cuenta», «su propia…». Nada de «él», «ella», ni «lo»/«la» referidos a {p} («mirarlo», «cuidarla»): repetí «{p}» o reformulá («con solo mirar a {p}»). Lo mismo con «seguro», «dispuesto», «solo», «cansado», «atrapado» y similares: reformulá con verbos («se siente con seguridad», «está en condiciones de»), sustantivos («su sensibilidad») o adjetivos que no cambian («sensible», «capaz»). El rol tampoco lleva género: nada de «progenitor», «madre o padre», «hijo o hija»; usá «en su rol de crianza», «quien cría», «la otra generación». Para hablar de las dos personas juntas, «ambas personas» o «entre Persona A y Persona B», no «ellos». Nunca uses barras, «x», «@» ni «e» como terminación neutra.",
    },
    "pt": {
        "femenino": "{p} é mulher: todo adjetivo, particípio e pronome referido a {p} vai no "
                    "feminino («a si mesma», «segura», «ela», «olhá-la»), de forma consistente "
                    "em todo o texto.",
        "masculino": "{p} é homem: todo adjetivo, particípio e pronome referido a {p} vai no "
                     "masculino («a si mesmo», «seguro», «ele», «olhá-lo»), de forma consistente "
                     "em todo o texto.",
        "neutro": "Não se sabe o gênero de {p} e não é preciso marcá-lo: nenhum adjetivo, particípio ou pronome referido a {p} pode terminar em -o/-a. Nada de «a si mesmo» nem «a si mesma»: use «se percebe», «por conta própria», «sua própria…». Nada de «ele», «ela», nem «o»/«a» referidos a {p} («olhá-lo», «cuidá-la»): repita «{p}» ou reformule («só de olhar para {p}»). O mesmo vale para «seguro», «disposto», «sozinho», «cansado», «preso» e similares: reformule com verbos («se sente com segurança», «está em condições de»), substantivos («sua sensibilidade») ou adjetivos que não mudam («sensível», «capaz»). O papel também não leva gênero: nada de «progenitor», «mãe ou pai», «filho ou filha»; use «no seu papel de criação», «quem cria», «a outra geração». Para falar das duas pessoas juntas, «ambas as pessoas» ou «entre Pessoa A e Pessoa B», não «eles». Nunca use barras, «x», «@» nem «e» como terminação neutra.",
    },
    "en": {
        "femenino": "{p} is a woman: refer to {p} as she/her, consistently.",
        "masculino": "{p} is a man: refer to {p} as he/him, consistently.",
        "neutro": "{p}'s gender is unknown and must not be marked: never use he/him/his or "
                  "she/her/hers for {p}. Use they/them, or repeat «{p}». Roles without gender "
                  "too: «parent», «child», «sibling», never «mother», «father», «son», "
                  "«daughter», «brother» or «sister».",
    },
}


def instruccion_persona(genero: str, lang: str, persona: str) -> str:
    """Cómo concordar al hablar de `persona` («Persona A»). Vacío o
    desconocido es neutro, como en `instruccion`. A diferencia del lector, en
    inglés hay instrucción: la tercera persona sí marca género (he/she)."""
    por_idioma = _INSTRUCCIONES_PERSONA[lang]
    return (por_idioma.get(genero) or por_idioma["neutro"]).format(p=persona)


def instruccion_personas(generos: tuple[str, str], lang: str) -> str:
    """Las dos personas del vínculo, A y después B."""
    return " ".join(
        instruccion_persona(genero, lang, nombre_persona(letra, lang))
        for letra, genero in zip("AB", generos, strict=True)
    )
