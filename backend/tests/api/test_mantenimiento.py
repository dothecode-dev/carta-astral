"""El modo mantenimiento: dejar de aceptar trabajo antes de un deploy.

Un deploy mata el contenedor viejo con su hilo adentro, y con él el informe que
estuviera escribiendo. `reanudar_informes` lo rescata después, pero quien pagó
espera de más. La salida es no arrancar nada nuevo y esperar a que lo que hay
termine: eso es lo que prende `make deploy` antes de pushear.

El flag vive en la caché —que en producción es la base (`USE_DB_CACHE`)—, así
que sobrevive al deploy y lo ven los dos contenedores que conviven durante el
swap. Una variable de entorno no serviría: cambiarla en Coolify dispara
justamente el deploy que queremos ordenar.
"""

import pytest
from django.core.cache import cache

from api import mantenimiento
from api.models import Interpretation
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpio():
    cache.clear()
    yield
    cache.clear()


def test_por_defecto_esta_apagado():
    """Lo normal es no estar en mantenimiento: si el flag faltara o la caché se
    vaciara, el sitio tiene que quedar ABIERTO, no cerrado."""
    assert mantenimiento.activo() is False


def test_se_prende_y_se_apaga():
    mantenimiento.activar()
    assert mantenimiento.activo() is True

    mantenimiento.desactivar()
    assert mantenimiento.activo() is False


def test_el_estado_lo_puede_consultar_cualquiera(client):
    """Sin sesión: lo consulta `make deploy` desde afuera, y la web en cada
    request para decidir si muestra el cartel."""
    resp = client.get("/api/estado/")

    assert resp.status_code == 200
    assert resp.json() == {"mantenimiento": False, "generando": 0, "config_faltante": False}


# --- El faltante de configuración se ve sin leer logs, pero sin enumerar qué -
#
# El Ruling 7 cambió el fail-fast de arranque (RF8) por un log en stderr, para
# no tumbar todo el backend por una variable de una sola superficie (el login
# por mail). Ese criterio se mantiene. Pero un log que nadie lee y que
# `make deploy` no mira no es un control compensatorio real: acá se suma la
# misma señal al endpoint que YA consulta `make deploy` en cada despliegue y
# que la web ya sondea, sin agregar plumbing nuevo ni bloquear nada.
#
# `GET /api/estado/` es público. Un booleano no dice nada de nadie, pero la
# lista de nombres sí le dice a cualquiera qué parte del sistema está mal
# configurada — y este repo es cuidadoso justo con eso (los dos admin están en
# rutas no adivinables). El detalle con los nombres sigue existiendo, sólo que
# no en la respuesta pública: en el log de arranque (`config_faltante()` de
# `api/identity.py`, que sigue devolviendo la lista para eso).


def test_el_estado_avisa_si_falta_tombstone_hmac_key(client, settings):
    settings.TOMBSTONE_HMAC_KEY = ""
    resp = client.get("/api/estado/")

    assert resp.json()["config_faltante"] is True


def test_el_estado_no_avisa_nada_con_la_configuracion_completa(client, settings):
    settings.TOMBSTONE_HMAC_KEY = "clave-de-produccion"
    resp = client.get("/api/estado/")

    assert resp.json()["config_faltante"] is False


def test_el_estado_cuenta_lo_que_un_deploy_cortaria(client, make_chart, make_account):
    """`generando` son los hilos escribiendo AHORA, que es lo que hay que
    esperar antes de desplegar. Una fila incompleta sin lock no cuenta: ésa ya
    está caída y la retoma el cron."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    Interpretation.objects.create(
        chart=carta, account=cuenta, lang="es", tier="largo",
        prompt_version=PROMPT_VERSION, completa=False,
    )

    assert client.get("/api/estado/").json()["generando"] == 0

    from api.interpretation_service import _lock_key

    cache.set(_lock_key(carta, "largo"), "1", 600)

    assert client.get("/api/estado/").json()["generando"] == 1


def test_en_mantenimiento_no_se_arranca_un_informe(account_client, make_chart):
    """La puerta de verdad está acá y no en la web: el 503 lo decide el
    backend, así que da igual por dónde entre el pedido."""
    carta = make_chart(account=account_client.account)
    mantenimiento.activar()

    resp = account_client.post(
        f"/api/charts/{carta.uuid}/interpretation/", {"lang": "es", "tier": "largo"},
    )

    assert resp.status_code == 503
    assert Interpretation.objects.count() == 0


def test_en_mantenimiento_no_se_abre_un_checkout(account_client):
    """Cobrar y no poder entregar es la peor combinación posible."""
    mantenimiento.activar()

    resp = account_client.post("/api/checkout/", {"producto": "informe_natal"})

    assert resp.status_code == 503


def test_en_mantenimiento_se_sigue_leyendo_lo_ya_escrito(account_client, make_chart, make_account):
    """El mantenimiento frena lo que se ESCRIBE, no lo que ya está: quien
    espera su informe tiene que poder seguir viendo cómo avanza."""
    carta = make_chart(account=account_client.account)
    mantenimiento.activar()

    resp = account_client.get(
        f"/api/charts/{carta.uuid}/interpretation/estado?lang=es&tier=largo",
    )

    assert resp.status_code != 503
