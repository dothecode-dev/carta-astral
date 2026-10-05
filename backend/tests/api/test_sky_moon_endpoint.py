"""La Luna de ahora, para la página «el cielo de hoy».

Pública como `/api/sky/`, con el mismo muro: no recibe datos de nadie, así que
no puede devolver nada personal, y el cálculo se cachea por minuto.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

URL = "/api/sky/moon/"


@pytest.fixture(autouse=True)
def _limpiar_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_responde_sin_autenticacion():
    assert APIClient().get(URL).status_code == 200


@pytest.mark.django_db
def test_devuelve_la_fase_las_proximas_y_el_cambio_de_signo():
    body = APIClient().get(URL).json()

    assert set(body) == {
        "moment", "sign", "phase", "illumination", "waxing",
        "next_phases", "next_sign_change",
    }
    assert 0 <= body["illumination"] <= 100
    assert isinstance(body["waxing"], bool)
    assert sorted(p["phase"] for p in body["next_phases"]) == sorted(
        ["new_moon", "first_quarter", "full_moon", "last_quarter"]
    )
    assert set(body["next_sign_change"]) == {"sign", "moment"}


@pytest.mark.django_db
def test_los_instantes_son_iso_con_zona_y_posteriores_al_de_ahora():
    body = APIClient().get(URL).json()
    now = datetime.fromisoformat(body["moment"])

    assert body["moment"].endswith(":00+00:00")
    for p in body["next_phases"]:
        assert datetime.fromisoformat(p["moment"]) > now
    assert datetime.fromisoformat(body["next_sign_change"]["moment"]) > now


@pytest.mark.django_db
def test_dos_pedidos_en_el_mismo_minuto_calculan_una_sola_vez():
    from api import sky

    with patch.object(sky, "moon_state", wraps=sky.moon_state) as espia:
        APIClient().get(URL)
        APIClient().get(URL)

    assert espia.call_count == 1


@pytest.mark.django_db
def test_comparte_el_techo_por_ip_del_cielo():
    from api.sky import SkyMoonView, SkyView

    assert SkyMoonView.throttle_scope == SkyView.throttle_scope == "sky"
