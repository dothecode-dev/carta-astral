"""`.env.example` es el molde del `.env` de producción y tiene que estar completo.

La regla del repo dice que toda variable nueva se agrega acá, pero una regla
que sólo vive en prosa no se cumple sola: este test la convierte en un gate.

Se recorre todo `backend/`, no sólo `config/settings.py`: una variable leída
desde `api/` o `interpret/` cuenta igual, y limitar el barrido al settings daba
una cobertura falsa —el archivo podía quedar incompleto con el test en verde.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
EJEMPLO = BACKEND / ".env.example"

# `os.environ.get("X")` y `os.environ["X"]`.
LECTURA = re.compile(r"""os\.environ(?:\.get)?[(\[]\s*["']([A-Z][A-Z0-9_]*)["']""")

# Variables que el código no lee por `os.environ` y que igual hacen falta:
# `dj_database_url.config()` busca DATABASE_URL por su cuenta, y GUNICORN_WORKERS
# lo lee `entrypoint.sh`. Sin esta lista, el barrido no las ve y el molde sale
# incompleto justo en la que impide arrancar.
INVISIBLES = {"DATABASE_URL", "GUNICORN_WORKERS"}


def _leidas_por_el_codigo() -> set[str]:
    nombres: set[str] = set()
    for py in BACKEND.rglob("*.py"):
        partes = py.relative_to(BACKEND).parts
        if partes[0] in {".venv", "tests"} or "migrations" in partes:
            continue
        nombres |= set(LECTURA.findall(py.read_text()))
    return nombres | INVISIBLES


def _documentadas_en_el_molde() -> set[str]:
    documentadas: set[str] = set()
    for linea in EJEMPLO.read_text().splitlines():
        linea = linea.strip().lstrip("#").strip()  # las de la app van comentadas
        if "=" in linea:
            documentadas.add(linea.split("=", 1)[0].strip())
    return documentadas


def test_el_molde_documenta_todas_las_variables_que_el_codigo_lee():
    faltan = _leidas_por_el_codigo() - _documentadas_en_el_molde()

    assert not faltan, f"faltan en backend/.env.example: {sorted(faltan)}"


def test_el_molde_no_trae_ningun_valor_real():
    """El repo es público: el molde lleva el nombre, nunca el secreto."""
    sospechosas = []
    for linea in EJEMPLO.read_text().splitlines():
        limpia = linea.strip().lstrip("#").strip()
        if "=" not in limpia:
            continue
        nombre, valor = (p.strip() for p in limpia.split("=", 1))
        # Red amplia a propósito, para que una variable secreta nueva quede
        # cubierta sin que nadie se acuerde de listarla. Las excepciones son
        # explícitas: llevan una de esas palabras y no son secretos.
        secreta = (
            any(p in nombre for p in ("SECRET", "KEY", "AUTH", "PASSWORD", "TOKEN"))
            and nombre not in {"AUTH_RATE", "APP_AUTH_ENABLED"}
        )
        if secreta and valor and not valor.startswith("cambiar"):
            sospechosas.append(nombre)

    assert not sospechosas, f"valores que parecen reales: {sospechosas}"
