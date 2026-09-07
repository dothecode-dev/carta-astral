"""Dos canjes gratis a la vez sobre un cupón de un uso otorgan uno.

Postgres solamente: el lock de fila sobre `Cupon` que lo garantiza no existe
en SQLite (ver `tests/api/concurrencia.py`).
"""
import pytest

from api import analitica, compra_service, notificaciones
from api.models import Cupon, CuponUso
from tests.api.concurrencia import en_hilos, requiere_postgres

pytestmark = [pytest.mark.django_db(transaction=True), requiere_postgres]

URL = "/api/checkout/"


def test_veinte_hilos_sobre_un_regalo_de_cinco_usos_otorgan_cinco(make_account, settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    settings.STRIPE_SUCCESS_URL = "https://x/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"
    monkeypatch.setattr(notificaciones, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(analitica, "evento", lambda *a, **k: None)
    monkeypatch.setattr(compra_service, "arrancar_informe", lambda *a, **k: None)
    Cupon.objects.create(codigo="CINCO", porcentaje=100, productos=["informe_natal"], usos_maximos=5)
    from api.auth import create_session
    from rest_framework.test import APIClient

    tokens = [create_session(make_account()) for _ in range(20)]

    def pedir(i):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens[i]}")
        return c.post(URL, {"producto": "informe_natal", "cupon": "CINCO"}).status_code

    resultados, errores = en_hilos(pedir, 20)

    assert errores == []
    assert sorted(resultados) == [200] * 5 + [400] * 15
    assert CuponUso.objects.count() == 5
