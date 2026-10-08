"""Las frases fijas de la firma y de Vínculo no marcan el género del lector (RF5b).

Son texto versionado que se le muestra a cualquiera, elija el trato que elija:
tienen que estar en neutro. El test recorre todas las frases en español y en
portugués y falla si alguna contiene, como palabra entera y sin distinguir
mayúsculas:

- un adjetivo o participio de la lista cerrada (la de la medición del 07-10,
  ampliada con los que aparecen en los dos archivos referidos a una persona), o
- «alguien»/«alguém» seguido de una palabra con flexión -o/-a/-os/-as
  («alguien sereno»): el indefinido arrastra el masculino por defecto.

En Vínculo las personas son «una persona» y «la otra»: ese femenino gramatical
de «persona» no se toca, pero un adjetivo o participio predicado de ellas
(«la otra se siente comprendida») sí se lee como género y se reescribe.

Algunas coincidencias no marcan el género de nadie («cuidado» sustantivo, un
adjetivo que es del lugar o de la relación). Van a LISTA_BLANCA por ocurrencia:
frase, palabra y cuántas veces aparece, con el motivo. Una frase nueva, o una
aparición más de la misma palabra en una frase exceptuada, vuelve a fallar.
"""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "api" / "data"
ARCHIVOS = ("firma_frases.json", "vinculo_frases.json")
IDIOMAS = ("es", "pt")

# Firma: 36 claves (Sol, Luna y Ascendente × 12 signos). Vínculo: 75 (15 pares
# de planetas personales × 5 aspectos mayores). Por dos idiomas: 2 × (36 + 75).
# Si el número cambia, el test tiene que actualizarse a sabiendas: una carga que
# se saltee un idioma o un archivo no puede pasar en verde sin recorrer nada.
TOTAL_FRASES = 222

_ADJETIVOS = (
    # Medición del 07-10.
    "seguro", "atento", "cuidadoso", "tranquilo", "cansado", "dispuesto",
    "preparado", "obligado", "callado", "cerrado", "querido", "protegido",
    "sozinho", "pronto", "prolijo", "discreto", "solo",
    # Revisión: participios y adjetivos de los dos archivos referidos a una persona.
    "cuidado", "valorizado", "valorado", "comprendido", "compreendido",
    "entendido", "contenido", "acolhido", "errado", "sereno", "curioso",
    "reservado", "intenso", "franco", "directo", "direto", "maduro",
    "cercano", "próximo",
)
PALABRAS = (
    "vos misma", "vos mismo", "você mesma", "você mesmo",
    *(f"{base[:-1]}{fin}" for base in _ADJETIVOS for fin in ("o", "a")),
)
_PATRON = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(p) for p in PALABRAS)
    # Cuatro letras o más: deja afuera «alguien lo ve».
    + r"|(?:alguien|alguém)\s+\w{3,}[oa]s?"
    + r")(?!\w)",
    re.IGNORECASE,
)

# (archivo, idioma, clave, palabra) -> (veces permitidas, por qué no marca género).
LISTA_BLANCA: dict[tuple[str, str, str, str], tuple[int, str]] = {
    # Concuerda con «la primera impresión», no con quien lee.
    ("firma_frases.json", "es", "Ascendant|Can", "atenta"): (1, "adjetivo de «impresión»"),
    ("firma_frases.json", "pt", "Ascendant|Can", "atenta"): (1, "adjetivo de «impressão»"),
    # Es el apoyo el que es tranquilo, no una de las personas.
    ("vinculo_frases.json", "es", "Sun|Moon|sextile", "tranquilo"): (1, "adjetivo de «apoyo»"),
    ("vinculo_frases.json", "pt", "Sun|Moon|sextile", "tranquilo"): (1, "adjetivo de «apoio»"),
    # «Quando é cuidado com gestos»: el que es cuidado es el apoio.
    ("vinculo_frases.json", "pt", "Sun|Moon|sextile", "cuidado"): (1, "participio de «apoio»"),
    # «Un lugar seguro»: el adjetivo es del lugar (el vínculo).
    ("vinculo_frases.json", "es", "Moon|Moon|trine", "seguro"): (1, "adjetivo de «lugar»"),
    ("vinculo_frases.json", "pt", "Moon|Moon|trine", "seguro"): (1, "adjetivo de «lugar»"),
    # «Una sola mirada»: el adjetivo es de la mirada.
    ("vinculo_frases.json", "es", "Mercury|Mercury|opposition", "sola"): (1, "adjetivo de «mirada»"),
    # «Ninguém segura»: verbo «segurar» (nadie lo sostiene), no adjetivo.
    ("vinculo_frases.json", "pt", "Moon|Moon|conjunction", "segura"): (1, "verbo «segurar»"),
    # «Cuidado» sustantivo: «cuidado espontáneo», «cuidado mutuo», «acción y
    # cuidado», «con el cuidado».
    ("vinculo_frases.json", "es", "Sun|Moon|trine", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "pt", "Sun|Moon|trine", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "es", "Moon|Venus|conjunction", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "pt", "Moon|Venus|conjunction", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "es", "Moon|Mars|sextile", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "pt", "Moon|Mars|sextile", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "es", "Venus|Mars|opposition", "cuidado"): (1, "sustantivo"),
    ("vinculo_frases.json", "pt", "Venus|Mars|opposition", "cuidado"): (1, "sustantivo"),
    # «Importa tanto como el contenido»: sustantivo.
    ("vinculo_frases.json", "es", "Mercury|Venus|square", "contenido"): (1, "sustantivo"),
}


def _frases():
    for archivo in ARCHIVOS:
        datos = json.loads((DATA / archivo).read_text(encoding="utf-8"))
        for lang in IDIOMAS:
            for clave, texto in datos[lang].items():
                yield archivo, lang, clave, texto


def _ocurrencias(texto: str) -> Counter[str]:
    return Counter(re.sub(r"\s+", " ", m.group(1).lower()) for m in _PATRON.finditer(texto))


def _fallas():
    fallas = []
    for archivo, lang, clave, texto in _frases():
        for palabra, veces in _ocurrencias(texto).items():
            permitidas = LISTA_BLANCA.get((archivo, lang, clave, palabra), (0, ""))[0]
            if veces > permitidas:
                fallas.append(f"{archivo} [{lang}] {clave} «{palabra}» ×{veces}: {texto}")
    return fallas


def test_recorre_todas_las_frases():
    assert sum(1 for _ in _frases()) == TOTAL_FRASES


def test_ninguna_frase_fija_marca_el_genero():
    fallas = _fallas()
    assert not fallas, f"{len(fallas)} coincidencias marcan el género:\n" + "\n".join(fallas)


@pytest.mark.parametrize("entrada", sorted(LISTA_BLANCA))
def test_la_lista_blanca_cuenta_lo_que_hay(entrada):
    """Ni entradas muertas ni de más: la cantidad permitida es la que aparece."""
    archivo, lang, clave, palabra = entrada
    datos = json.loads((DATA / archivo).read_text(encoding="utf-8"))
    assert _ocurrencias(datos[lang][clave])[palabra] == LISTA_BLANCA[entrada][0], entrada
