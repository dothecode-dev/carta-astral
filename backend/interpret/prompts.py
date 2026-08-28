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
TRANSLATE_MAX_TOKENS = 2000

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
