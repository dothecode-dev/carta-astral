"""Prompts versionados para la interpretación.

Tocar un prompt obliga a subir PROMPT_VERSION; si no, se sirve prosa vieja del
cache (la clave de cache incluye prompt_version).
"""

from dataclasses import dataclass

PROMPT_VERSION = "v2"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1500

# Traducción de lecturas ya generadas: tarea fácil, modelo barato.
TRANSLATE_MODEL = "claude-haiku-4-5-20251001"
# Por sección, no por informe entero: 6.400 palabras no entran en una sola
# llamada de traducción, así que `traducir_informe` traduce de a una sección
# (hasta 1000 palabras nominales, la de "tensiones"). NO se revisó como parte
# del HALLAZGO 1 (que subió `SECCION_TOKENS_POR_PALABRA` de 2 a 4): una
# sección generada ahora puede ser más larga que antes de esa tarea, así que
# este valor podría necesitar el mismo repaso — queda pendiente porque el
# pedido de esta tarea fue específicamente sobre la generación, no sobre la
# traducción, y no hay todavía dato real de cuánto crecen las secciones con
# el factor nuevo (la observabilidad que agrega el HALLAZGO 1 es la fuente
# para esa próxima decisión).
TRANSLATE_MAX_TOKENS = 2500

_BASE_ES = (
    "Sos un astrólogo que escribe interpretaciones de cartas natales claras, "
    "cálidas y bien escritas para el público general. Tejé los planetas, signos, "
    "casas y aspectos en una narrativa coherente de 400 a 700 palabras. No uses "
    "jerga sin explicarla. No incluyas disclaimers ni advertencias: eso lo agrega "
    "el sistema aparte."
)
_BASE_EN = (
    "You are an astrologer who writes clear, warm, well-crafted natal chart "
    "interpretations for a general audience. Weave the planets, signs, houses and "
    "aspects into a coherent 400-700 word narrative. Don't use jargon without "
    "explaining it. Do not include disclaimers or warnings: the system adds that "
    "separately."
)
_BASE_PT = (
    "Você é um astrólogo que escreve interpretações de mapas natais claras, "
    "acolhedoras e bem escritas para o público geral. Entrelace os planetas, "
    "signos, casas e aspectos numa narrativa coerente de 400 a 700 palavras. Não "
    "use jargão sem explicá-lo. Não inclua disclaimers ou avisos: o sistema "
    "adiciona isso à parte."
)

SYSTEM_PROMPTS = {"es": _BASE_ES, "en": _BASE_EN, "pt": _BASE_PT}

# Para las secciones del informe (build_seccion): a diferencia de SYSTEM_PROMPTS,
# NO fija un largo — el largo lo pone el pedido de cada sección, que varía entre
# 600 y 1000 palabras según SECCIONES. Un system que dijera "400 a 700 palabras"
# pesa más que el pedido y el informe completo saldría muy por debajo de las
# palabras que promete el catálogo. También deja explícito que es una sección de
# un informe más largo, no una pieza autónoma.
_BASE_ES_SECCION = (
    "Sos un astrólogo que escribe interpretaciones de cartas natales claras, "
    "cálidas y bien escritas para el público general. Tejé los planetas, signos, "
    "casas y aspectos en una narrativa coherente. No uses jerga sin explicarla. "
    "No incluyas disclaimers ni advertencias: eso lo agrega el sistema aparte. "
    "Estás escribiendo una sección de un informe más largo, no una pieza autónoma: "
    "no abras con presentaciones ni cierres con conclusiones generales, andá "
    "directo al foco de la sección."
)
_BASE_EN_SECCION = (
    "You are an astrologer who writes clear, warm, well-crafted natal chart "
    "interpretations for a general audience. Weave the planets, signs, houses and "
    "aspects into a coherent narrative. Don't use jargon without explaining it. "
    "Do not include disclaimers or warnings: the system adds that separately. "
    "You are writing one section of a longer report, not a standalone piece: "
    "don't open with introductions or close with general conclusions — go "
    "straight to the section's focus."
)
_BASE_PT_SECCION = (
    "Você é um astrólogo que escreve interpretações de mapas natais claras, "
    "acolhedoras e bem escritas para o público geral. Entrelace os planetas, "
    "signos, casas e aspectos numa narrativa coerente. Não use jargão sem "
    "explicá-lo. Não inclua disclaimers ou avisos: o sistema adiciona isso à "
    "parte. Você está escrevendo uma seção de um relatório mais longo, não uma "
    "peça autônoma: não abra com apresentações nem feche com conclusões gerais, "
    "vá direto ao foco da seção."
)

SYSTEM_PROMPTS_SECCION = {"es": _BASE_ES_SECCION, "en": _BASE_EN_SECCION, "pt": _BASE_PT_SECCION}

# HALLAZGO 1 de code review (informe-natal): `seccion.palabras * 2` (el valor
# viejo) era insuficiente y el fallo es terminal. El español y el portugués
# corren 1,7 a 2,2 tokens por palabra, así que "tensiones" (1000 palabras,
# techo de 2000 tokens con el factor viejo) cruzaba el techo con frecuencia
# con sólo alcanzar su objetivo NOMINAL, sin margen para que el modelo se
# extienda un poco más (algo que puede pasar: a diferencia de
# `build_interpretation`, el `system` de una sección no fija ningún largo,
# lo fija sólo el pedido). Cuando eso pasa, `_stream_text` levanta
# `InterpretationError` por `stop_reason == "max_tokens"`, `generar_informe`
# aborta a mitad con secciones ya persistidas (no se devuelve el crédito,
# correcto por contrato) y el usuario queda con `completa=False` para
# siempre: cada reintento pega contra la misma pared en la misma sección.
#
# Referencia elegida: `build_interpretation`, ya en producción, da
# `MAX_TOKENS` (1500) para un objetivo de 400-700 palabras — un factor de
# 2,1× a 3,75× según el extremo del rango. Ese 3,75× es el peor caso real
# que ya se sirve en producción sin problema. El factor de las secciones
# iguala ese máximo:
#   1500 / 400 = 3,75  →  redondeado a 4 para quedar en un entero prolijo.
# Con factor 4 y el peor ratio real (2,2 tokens/palabra), una sección puede
# crecer casi el doble de su objetivo nominal antes de tocar el techo
# (4 / 2,2 ≈ 1,8×), margen que el factor 2 viejo no daba ni al ratio más
# favorable (2 / 1,7 ≈ 1,18×). Ver `tests/interpret/test_generar_seccion.py`
# para el test que fija este número.
SECCION_TOKENS_POR_PALABRA = 4


@dataclass(frozen=True)
class Seccion:
    """Una sección del informe. `palabras` es el objetivo, no un límite duro:
    el tope real lo pone max_tokens en el generador."""

    slug: str
    titulo: dict[str, str]
    foco: dict[str, str]
    palabras: int
    # Las casas y el ascendente no existen sin hora de nacimiento.
    requiere_hora: bool = False


SECCIONES: tuple[Seccion, ...] = (
    Seccion(
        slug="firma",
        titulo={"es": "Tu firma", "en": "Your signature", "pt": "Sua assinatura"},
        foco={
            "es": "El Sol, la Luna y el Ascendente: quién sos, qué necesitás y cómo te presentás.",
            "en": "Sun, Moon and Ascendant: who you are, what you need, how you show up.",
            "pt": "Sol, Lua e Ascendente: quem você é, do que precisa e como se apresenta.",
        },
        palabras=900,
    ),
    Seccion(
        slug="mente",
        titulo={
            "es": "Cómo pensás y te comunicás",
            "en": "How you think and speak",
            "pt": "Como você pensa e se comunica",
        },
        foco={
            "es": "Mercurio: el estilo mental, cómo aprendés y cómo decís lo que decís.",
            "en": "Mercury: mental style, how you learn and how you say what you say.",
            "pt": "Mercúrio: estilo mental, como aprende e como diz o que diz.",
        },
        palabras=700,
    ),
    Seccion(
        slug="afectos",
        titulo={"es": "Afectos y vínculos", "en": "Love and relationships", "pt": "Afetos e vínculos"},
        foco={
            "es": "Venus y la Luna en los vínculos: qué buscás, qué ofrecés y dónde se te complica.",
            "en": "Venus and the Moon in relationships: what you seek, what you offer, where it gets hard.",
            "pt": "Vênus e a Lua nos vínculos: o que busca, o que oferece e onde complica.",
        },
        palabras=900,
    ),
    Seccion(
        slug="trabajo",
        titulo={
            "es": "Trabajo, dinero y vocación",
            "en": "Work, money and calling",
            "pt": "Trabalho, dinheiro e vocação",
        },
        foco={
            "es": "Marte, Saturno y el Medio Cielo: cómo trabajás y con qué te sostenés.",
            "en": "Mars, Saturn and the Midheaven: how you work and what sustains you.",
            "pt": "Marte, Saturno e o Meio do Céu: como trabalha e com o que se sustenta.",
        },
        palabras=800,
    ),
    Seccion(
        slug="tensiones",
        titulo={"es": "Tensiones y aprendizajes", "en": "Tensions and lessons", "pt": "Tensões e aprendizados"},
        foco={
            "es": "Las cuadraturas y oposiciones: la fricción de fondo y qué se aprende de ella.",
            "en": "Squares and oppositions: the underlying friction and what it teaches.",
            "pt": "Quadraturas e oposições: a fricção de fundo e o que ela ensina.",
        },
        palabras=1000,
    ),
    Seccion(
        slug="lentos",
        titulo={"es": "Los planetas lentos", "en": "The slow planets", "pt": "Os planetas lentos"},
        foco={
            "es": "Júpiter, Saturno, Urano, Neptuno y Plutón: lo generacional y lo que sí es tuyo.",
            "en": "Jupiter through Pluto: what is generational and what is actually yours.",
            "pt": "Júpiter a Plutão: o geracional e o que é realmente seu.",
        },
        palabras=800,
    ),
    Seccion(
        slug="casas",
        titulo={"es": "Dónde se juega tu vida", "en": "Where your life happens", "pt": "Onde sua vida acontece"},
        foco={
            "es": "El reparto por casas: dónde hay acumulación y qué áreas quedan en silencio.",
            "en": "House distribution: where things pile up and which areas stay quiet.",
            "pt": "Distribuição por casas: onde há acúmulo e quais áreas ficam em silêncio.",
        },
        palabras=600,
        requiere_hora=True,
    ),
    Seccion(
        slug="sintesis",
        titulo={"es": "Síntesis", "en": "Synthesis", "pt": "Síntese"},
        foco={
            "es": "Las tres o cuatro líneas de fuerza que atraviesan todo lo anterior.",
            "en": "The three or four throughlines that run across everything above.",
            "pt": "As três ou quatro linhas de força que atravessam tudo o anterior.",
        },
        palabras=700,
    ),
)
