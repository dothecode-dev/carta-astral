"""El timeout del cliente Anthropic tiene que aguantar una sección larga.

El 01-09-2026 el informe pago de la carta 8 se cortó en la sección 3 con
`httpx.ReadTimeout`, y el 02-09 el reintento se cortó igual. El cliente se
construía con `timeout=25.0`: como la generación va por streaming ese timeout
es POR CHUNK, así que cualquier hueco de más de 25 segundos entre pedazos mata
el intento entero. Las dos secciones que sí habían salido tardaron 42 y 25
segundos entre punta y punta — estaba en el filo.

Ese intento no es gratis: `completar_generacion` lo cuenta contra
`INTENTOS_MAXIMOS` y al tercero devuelve el derecho y borra lo escrito. Un
timeout corto no "reintenta más rápido": gasta los tres intentos y le
devuelve la plata a alguien que quería su informe.
"""

import pytest

from api import interpretation_service as svc


@pytest.fixture
def con_api_key(settings):
    """`_build_client` corta antes de construir nada si no hay key, y en los
    tests no hay (ver `test_devolucion_informe.py::build_seccion_falla`)."""
    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"


def test_el_timeout_aguanta_una_seccion_lenta(con_api_key):
    """No es un número mágico: es el tiempo que puede pasar entre dos chunks
    de una sección de 1000 palabras cuando el modelo está cargado. 25 segundos
    no alcanzaba y costó dos intentos de un informe pago."""
    assert svc._build_client().timeout.read >= 120


def test_el_timeout_de_conexion_sigue_siendo_corto(con_api_key):
    """Esperar por un chunk que está viniendo es una cosa; esperar por un
    handshake que no va a pasar es otra. Si la API no está accesible conviene
    fallar rápido y dejar que el próximo intento lo tome."""
    assert svc._build_client().timeout.connect <= 15
