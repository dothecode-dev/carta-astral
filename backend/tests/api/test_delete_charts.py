import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.deletion import delete_account
from api.models import Account, BirthData, Chart, CreditTransaction


def _client(acc):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    return c


PAYLOAD = {"date": "1990-05-20", "time": "10:30", "lat": -34.6, "lng": -58.4}


@pytest.mark.django_db
def test_delete_all_charts_scoped_to_account():
    a = Account.objects.create()
    b = Account.objects.create()
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    _client(b).post("/api/charts/", PAYLOAD, format="json")

    resp = _client(a).delete("/api/charts/")

    assert resp.status_code == 204
    assert _client(a).get("/api/charts/").data["results"] == []
    # las cartas de otra cuenta quedan intactas
    assert len(_client(b).get("/api/charts/").data["results"]) == 1
    # los datos de nacimiento (nombre, fecha, coordenadas) no quedan huérfanos
    assert BirthData.objects.count() == 1  # sólo el de la carta de B


@pytest.mark.django_db
def test_delete_charts_requires_auth():
    assert APIClient().delete("/api/charts/").status_code == 401


@pytest.mark.django_db
def test_delete_charts_preserva_ledger(monkeypatch, settings):
    """Borrar cartas cascadea interpretaciones pero NUNCA borra transacciones de créditos."""
    import api.interpretation_service as svc

    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: object())
    monkeypatch.setattr(svc, "build_interpretation", lambda *a, **kw: "fake text")

    a = Account.objects.create()
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    uuid = resp.data["id"]
    resp = _client(a).post(f"/api/charts/{uuid}/interpretation/", {"lang": "es"}, format="json")
    assert resp.status_code == 200
    txns_antes = CreditTransaction.objects.count()
    assert txns_antes > 0

    assert _client(a).delete("/api/charts/").status_code == 204

    assert Chart.objects.filter(account=a).count() == 0
    assert CreditTransaction.objects.count() == txns_antes
    # el FK a la interpretación borrada queda en NULL, no arrastra la fila
    assert CreditTransaction.objects.filter(kind="consumption", interpretation__isnull=True).exists()


@pytest.mark.django_db
def test_delete_account_borra_birth_data():
    """El borrado de cuenta debe llevarse también los datos de nacimiento (dato personal)."""
    a = Account.objects.create()
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert BirthData.objects.count() == 1

    delete_account(a)

    assert BirthData.objects.count() == 0
