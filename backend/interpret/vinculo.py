"""El informe de Vínculo (RF21): ocho secciones sobre la INTERACCIÓN entre dos
personas, con la lente del tipo de vínculo. Sin Django (lint-imports).

El modelo escribe «Persona A» / «Persona B» —o el rol, si lo hay— y nunca un
nombre: los alias no entran al prompt (RF22) y se sustituyen al mostrar."""

import json

from interpret.generator import _MARGEN_TOPE_SECCION, _stream_text
from interpret.prompts import MODEL, SECCION_TOKENS_POR_PALABRA, Seccion
from interpret.trato import instruccion_personas, nombre_persona

# El rol con el género de la persona, artículo incluido (decisión del
# 10-10-2026: el género se pregunta por persona y es opcional). La clave "" es
# la forma neutra —la de quien no lo dijo o eligió «neutro»— y la única cuando
# el género no cambia la etiqueta. La neutra no lleva sustantivo con género
# («madre o padre»): es lo que la guía neutra le prohíbe al modelo.
ETIQUETAS_ROL: dict[str, dict[str, dict[str, str]]] = {
    "jefe": {
        "es": {"": "quien dirige el trabajo de la otra persona", "femenino": "la jefa", "masculino": "el jefe"},
        "en": {"": "the manager"},
        "pt": {"": "quem dirige o trabalho da outra pessoa", "femenino": "a chefe", "masculino": "o chefe"},
    },
    "equipo": {
        "es": {"": "integrante del equipo"},
        "en": {"": "the team member"},
        "pt": {"": "integrante da equipe"},
    },
    "socio": {
        "es": {"": "parte de la misma sociedad", "femenino": "la socia", "masculino": "el socio"},
        "en": {"": "the business partner"},
        "pt": {"": "parte da mesma sociedade", "femenino": "a sócia", "masculino": "o sócio"},
    },
    "colega": {
        "es": {"": "colega", "femenino": "la colega", "masculino": "el colega"},
        "en": {"": "the colleague"},
        "pt": {"": "colega", "femenino": "a colega", "masculino": "o colega"},
    },
    "progenitor": {
        "es": {"": "quien tiene el rol de crianza", "femenino": "la madre", "masculino": "el padre"},
        "en": {"": "the parent", "femenino": "the mother", "masculino": "the father"},
        "pt": {"": "quem tem o papel de criação", "femenino": "a mãe", "masculino": "o pai"},
    },
    "hijo": {
        "es": {"": "quien recibió la crianza de la otra persona", "femenino": "la hija", "masculino": "el hijo"},
        "en": {"": "the child", "femenino": "the daughter", "masculino": "the son"},
        "pt": {"": "quem recebeu a criação da outra pessoa", "femenino": "a filha", "masculino": "o filho"},
    },
    "hermano": {
        "es": {"": "quien comparte la familia de origen", "femenino": "la hermana", "masculino": "el hermano"},
        "en": {"": "the sibling", "femenino": "the sister", "masculino": "the brother"},
        "pt": {"": "quem compartilha a família de origem", "femenino": "a irmã", "masculino": "o irmão"},
    },
    "otro_familiar": {
        "es": {"": "familiar", "femenino": "una familiar", "masculino": "un familiar"},
        "en": {"": "a relative"},
        "pt": {"": "familiar", "femenino": "uma familiar", "masculino": "um familiar"},
    },
}


def _por_genero(tabla: dict[str, str], genero: str) -> str:
    return tabla.get(genero, tabla[""])


TIPO: dict[str, dict[str, str]] = {
    "pareja": {"es": "pareja", "en": "romantic partners", "pt": "casal"},
    "trabajo": {"es": "trabajo", "en": "work", "pt": "trabalho"},
    "familia": {"es": "familia", "en": "family", "pt": "família"},
    "amistad": {"es": "amistad", "en": "friendship", "pt": "amizade"},
}



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
           "sin jerga sin explicar. Nombrá a cada persona SIEMPRE como «Persona A» o «Persona B»: "
           "el rol es contexto («Persona A, como madre, …»), no un nombre; nunca inventes nombres. No incluyas disclaimers. "
           "Escribís una sección de un informe más largo: andá directo a su foco."),
    "en": ("You are an astrologer writing about the relationship between two people from "
           "their natal charts: the interaction, not each chart on its own. Clear, warm, no "
           "unexplained jargon. ALWAYS refer to each person as “Person A” or “Person B”: the role "
           "is context (“Person A, as the parent, …”), not a name; never invent names. No disclaimers. You are writing "
           "one section of a longer report: go straight to its focus."),
    "pt": ("Você é um astrólogo que escreve sobre a relação entre duas pessoas a partir de "
           "seus mapas natais: a interação, não cada mapa separado. Claro, acolhedor, sem "
           "jargão sem explicar. Chame cada pessoa SEMPRE de «Pessoa A» ou «Pessoa B»: o papel "
           "é contexto («Pessoa A, como mãe, …»), não um nome; nunca invente nomes. Sem disclaimers. Você escreve uma seção de "
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
_ES_ROL = {"es": "{p} es {rol}.", "en": "{p} is {rol}.", "pt": "{p} é {rol}."}
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
        _ES_ROL[lang].format(
            p=nombre_persona(letra, lang),
            rol=_por_genero(ETIQUETAS_ROL[p["rol"]][lang], p.get("genero", "")),
        )
        for letra, p in personas if p["rol"]
    )
    generos = instruccion_personas(
        (datos["persona_a"].get("genero", ""), datos["persona_b"].get("genero", "")), lang,
    )
    roles = f"{roles} {generos}".strip()
    texto = _PEDIDO[lang].format(
        tipo=TIPO[datos["tipo"]][lang], roles=roles, titulo=seccion.titulo[lang],
        foco=seccion.foco[lang], palabras=seccion.palabras,
        maximo=int(seccion.palabras * _MARGEN_TOPE_SECCION),
    )
    # El género ya está dicho en la instrucción de concordancia: repetirlo en
    # el JSON no le suma nada al modelo.
    sin_genero = {
        **datos,
        **{k: {c: v for c, v in datos[k].items() if c != "genero"}
           for k in ("persona_a", "persona_b")},
    }
    texto += "\n\n" + json.dumps(sin_genero, ensure_ascii=False)
    for letra, p in personas:
        if not p["carta"].get("time_known", True):
            texto += _SIN_HORA[lang].format(p=nombre_persona(letra, lang))
    if previo:
        texto += _PREVIO[lang].format(previo=previo)
    return texto


def build_seccion_vinculo(datos: dict, seccion: Seccion, lang: str, previo: str, client) -> str:
    system = [{"type": "text", "text": _SYSTEM[lang]}]
    # Sin razonar (decisión del 10-10-2026): Sonnet 5 razona por defecto, y
    # con la guía neutra larga una sección se gastó en pensar los 8.400 tokens
    # de su techo y el informe falló. El techo mide texto; el género lo
    # revisa el juez de cada persona después.
    return _stream_text(
        client, MODEL, system, contenido_vinculo(datos, seccion, lang, previo),
        seccion.palabras * SECCION_TOKENS_POR_PALABRA, thinking={"type": "disabled"},
    )
