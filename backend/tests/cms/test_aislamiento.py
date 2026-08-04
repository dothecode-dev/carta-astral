"""El CMS no puede ser la puerta trasera a los datos de la aplicación.

`api/admin.py` establece que el panel no expone datos de nacimiento. Un editor
del CMS no puede tener por otro camino lo que ahí se evitó.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_import_linter_cubre_el_cms():
    pyproject = (RAIZ / "pyproject.toml").read_text()
    assert '"cms"' in pyproject, "cms no está entre los root_packages de import-linter"


def test_los_contratos_pasan():
    # `python -m importlinter.cli lint` no ejecuta nada: el módulo no tiene
    # bloque `__main__` que invoque el comando de click. Se usa el binario
    # `lint-imports` del venv, ubicado junto al intérprete que corre pytest.
    lint_imports = Path(sys.executable).parent / "lint-imports"
    r = subprocess.run(
        [str(lint_imports)],
        cwd=RAIZ, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
