"""El informe de Vínculo (RF21): ocho secciones sobre la INTERACCIÓN entre dos
personas, con la lente del tipo de vínculo. Sin Django (lint-imports).

El modelo escribe «Persona A» / «Persona B» —o el rol, si lo hay— y nunca un
nombre: los alias no entran al prompt (RF22) y se sustituyen al mostrar."""

import json

from interpret.generator import _MARGEN_TOPE_SECCION, _stream_text
from interpret.prompts import MODEL, SECCION_TOKENS_POR_PALABRA, Seccion

ETIQUETAS_ROL: dict[str, dict[str, str]] = {
    "jefe": {"es": "jefe o jefa", "en": "manager", "pt": "chefe"},
    "equipo": {"es": "integrante del equipo", "en": "team member", "pt": "integrante da equipe"},
    "socio": {"es": "socio o socia", "en": "business partner", "pt": "sócio ou sócia"},
    "colega": {"es": "colega", "en": "colleague", "pt": "colega"},
    "progenitor": {"es": "madre o padre", "en": "parent", "pt": "mãe ou pai"},
    "hijo": {"es": "hijo o hija", "en": "child", "pt": "filho ou filha"},
    "hermano": {"es": "hermano o hermana", "en": "sibling", "pt": "irmão ou irmã"},
    "otro_familiar": {"es": "familiar", "en": "relative", "pt": "familiar"},
}

TIPO: dict[str, dict[str, str]] = {
    "pareja": {"es": "pareja", "en": "romantic partners", "pt": "casal"},
    "trabajo": {"es": "trabajo", "en": "work", "pt": "trabalho"},
    "familia": {"es": "familia", "en": "family", "pt": "família"},
    "amistad": {"es": "amistad", "en": "friendship", "pt": "amizade"},
}

_PERSONA = {"es": "Persona {}", "en": "Person {}", "pt": "Pessoa {}"}


def _s(slug, titulo, foco, palabras, requiere_hora=False) -> Seccion:
    return Seccion(slug=slug, titulo=titulo, foco=foco, palabras=palabras, requiere_hora=requiere_hora)


SECCIONES_VINCULO: tuple[Seccion, ...] = (
    _s("encuentro",
       {"es": "Cómo se encuentran", "en": "How you meet", "pt": "Como vocês se encontram"},
       {"es": "La química de base: Sol, Luna y Ascendentes cruzados, qué se reconoce de entrada.",
        "en": "The basic chemistry: crossed Suns, Moons and Ascendants, what each recognizes at once.",
        "pt": "A química de base: Sóis, Luas e Ascendentes cruzados, o que se reconhece de cara."},
       800),
    _s("aporte",
       {"es": "Qué trae cada uno", "en": "What each brings", "pt": "O que cada um traz"},
       {"es": "Lo que cada persona pone en la relación según su carta, mirado desde el vínculo.",
        "en": "What each person puts into the relationship, seen through the bond.",
        "pt": "O que cada pessoa coloca na relação, visto a partir do vínculo."},
       800),
    _s("comunicacion",
       {"es": "Cómo se hablan", "en": "How you talk", "pt": "Como vocês conversam"},
       {"es": "Mercurio de cada uno y sus aspectos cruzados: malentendidos y sintonías.",
        "en": "Each Mercury and its crossed aspects: misunderstandings and attunement.",
        "pt": "Mercúrio de cada um e seus aspectos cruzados: mal-entendidos e sintonias."},
       700),
    _s("afecto",
       {"es": "Afecto y cuidado", "en": "Affection and care", "pt": "Afeto e cuidado"},
       {"es": "Venus y la Luna cruzados: cómo se demuestran el cariño y qué necesita cada uno.",
        "en": "Crossed Venus and Moon: how affection is shown and what each needs.",
        "pt": "Vênus e Lua cruzados: como demonstram carinho e do que cada um precisa."},
       800),
    _s("choque",
       {"es": "Energía y choque", "en": "Energy and friction", "pt": "Energia e atrito"},
       {"es": "Marte, cuadraturas y oposiciones: dónde chocan y qué hacer con eso.",
        "en": "Mars, squares and oppositions: where you clash and what to do with it.",
        "pt": "Marte, quadraturas e oposições: onde se chocam e o que fazer com isso."},
       800),
    _s("tiempo",
       {"es": "Lo que sostiene en el tiempo", "en": "What lasts", "pt": "O que sustenta no tempo"},
       {"es": "Saturno y Júpiter cruzados: compromiso, crecimiento y lo que pesa.",
        "en": "Crossed Saturn and Jupiter: commitment, growth and what weighs.",
        "pt": "Saturno e Júpiter cruzados: compromisso, crescimento e o que pesa."},
       700),
    _s("casas",
       {"es": "Dónde cae cada uno en la vida del otro",
        "en": "Where each lands in the other's life",
        "pt": "Onde cada um cai na vida do outro"},
       {"es": "En qué casas del otro caen los planetas de cada uno (sólo hacia quien tiene hora).",
        "en": "Which of the other's houses each one's planets fall into (only toward whoever has a birth time).",
        "pt": "Em que casas do outro caem os planetas de cada um (só para quem tem hora)."},
       700, requiere_hora=True),
    _s("sintesis",
       {"es": "Síntesis y consejos", "en": "Summary and advice", "pt": "Síntese e conselhos"},
       {"es": "Lo esencial del vínculo y consejos concretos según el tipo de relación.",
        "en": "The core of the bond and concrete advice for this kind of relationship.",
        "pt": "O essencial do vínculo e conselhos concretos para esse tipo de relação."},
       700),
)

_AFECTO_TRABAJO = _s(
    "afecto",
    {"es": "Confianza y reconocimiento", "en": "Trust and recognition", "pt": "Confiança e reconhecimento"},
    {"es": "Venus y la Luna cruzados en clave de trabajo: cómo se reconocen y en qué confían.",
     "en": "Crossed Venus and Moon at work: how you acknowledge each other and what you trust.",
     "pt": "Vênus e Lua cruzados no trabalho: como se reconhecem e em que confiam."},
    800,
)


def secciones_vinculo(tipo: str, hay_hora: bool) -> list[Seccion]:
    secciones = [_AFECTO_TRABAJO if (tipo == "trabajo" and s.slug == "afecto") else s
                 for s in SECCIONES_VINCULO]
    return [s for s in secciones if hay_hora or not s.requiere_hora]


_SYSTEM = {
    "es": ("Sos un astrólogo que escribe sobre la relación entre dos personas a partir de "
           "sus cartas natales: la interacción, no cada carta por separado. Claro, cálido, "
           "sin jerga sin explicar. Nombrá a cada persona SÓLO como «Persona A» o «Persona B», "
           "o por su rol si lo tiene; nunca inventes nombres. No incluyas disclaimers. "
           "Escribís una sección de un informe más largo: andá directo a su foco."),
    "en": ("You are an astrologer writing about the relationship between two people from "
           "their natal charts: the interaction, not each chart on its own. Clear, warm, no "
           "unexplained jargon. Refer to each person ONLY as “Person A” or “Person B”, or by "
           "their role if they have one; never invent names. No disclaimers. You are writing "
           "one section of a longer report: go straight to its focus."),
    "pt": ("Você é um astrólogo que escreve sobre a relação entre duas pessoas a partir de "
           "seus mapas natais: a interação, não cada mapa separado. Claro, acolhedor, sem "
           "jargão sem explicar. Chame cada pessoa SÓ de «Pessoa A» ou «Pessoa B», ou pelo "
           "papel se tiver; nunca invente nomes. Sem disclaimers. Você escreve uma seção de "
           "um relatório mais longo: vá direto ao foco."),
}

_PEDIDO = {
    "es": ("Vínculo de tipo {tipo}. {roles}\nSección: «{titulo}». Foco: {foco}\n"
           "Unas {palabras} palabras; no superes las {maximo}. Datos de las dos cartas y de "
           "cómo se miran:"),
    "en": ("Relationship type: {tipo}. {roles}\nSection: “{titulo}”. Focus: {foco}\n"
           "About {palabras} words; do not exceed {maximo}. Data for both charts and how they "
           "relate:"),
    "pt": ("Vínculo do tipo {tipo}. {roles}\nSeção: «{titulo}». Foco: {foco}\n"
           "Cerca de {palabras} palavras; não passe de {maximo}. Dados dos dois mapas e de "
           "como se olham:"),
}
_ES_ROL = {"es": "{p} es {rol}.", "en": "{p} is the {rol}.", "pt": "{p} é {rol}."}
_SIN_HORA = {
    "es": "\n\nSin hora de nacimiento para {p}: no interpretes su Ascendente ni sus casas.",
    "en": "\n\nNo birth time for {p}: do not interpret their Ascendant or houses.",
    "pt": "\n\nSem hora de nascimento para {p}: não interprete o Ascendente nem as casas.",
}
_PREVIO = {
    "es": "\n\nYa se escribió esto (no lo repitas):\n{previo}",
    "en": "\n\nAlready written (don't repeat it):\n{previo}",
    "pt": "\n\nJá foi escrito (não repita):\n{previo}",
}


def contenido_vinculo(datos: dict, seccion: Seccion, lang: str, previo: str) -> str:
    personas = (("A", datos["persona_a"]), ("B", datos["persona_b"]))
    roles = " ".join(
        _ES_ROL[lang].format(p=_PERSONA[lang].format(letra), rol=ETIQUETAS_ROL[p["rol"]][lang])
        for letra, p in personas if p["rol"]
    )
    texto = _PEDIDO[lang].format(
        tipo=TIPO[datos["tipo"]][lang], roles=roles, titulo=seccion.titulo[lang],
        foco=seccion.foco[lang], palabras=seccion.palabras,
        maximo=int(seccion.palabras * _MARGEN_TOPE_SECCION),
    )
    texto += "\n\n" + json.dumps(datos, ensure_ascii=False)
    for letra, p in personas:
        if not p["carta"].get("time_known", True):
            texto += _SIN_HORA[lang].format(p=_PERSONA[lang].format(letra))
    if previo:
        texto += _PREVIO[lang].format(previo=previo)
    return texto


def build_seccion_vinculo(datos: dict, seccion: Seccion, lang: str, previo: str, client) -> str:
    system = [{"type": "text", "text": _SYSTEM[lang]}]
    return _stream_text(
        client, MODEL, system, contenido_vinculo(datos, seccion, lang, previo),
        seccion.palabras * SECCION_TOKENS_POR_PALABRA,
    )
