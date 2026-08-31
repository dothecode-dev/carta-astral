import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.canje import otorgar
from api.deletion import delete_account
from api.models import Account, BirthData, Chart, Movimiento


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
    """Borrar cartas cascadea interpretaciones pero NUNCA borra el rastro de
    plata. Task 11: el cobro ya no deja `CreditTransaction` (eso lo hacía
    `ledger.charge`, que `interpretation_service` dejó de usar) sino
    `Movimiento` (`canje.canjear`) — el invariante que importa es el mismo:
    el `Movimiento` de consumo sobrevive al borrado de la carta, sólo su FK
    a `chart` queda en NULL (`SET_NULL`, igual que antes con
    `CreditTransaction.interpretation`)."""
    import api.interpretation_service as svc

    settings.INTERPRETATION_DAILY_CAP = 100
    # (El segundo mock era de `build_interpretation`, del flujo viejo de
    # interpretación que la Task 0 retiró: la generación real ya no pasa por
    # ahí, sólo por `_build_client` dentro de `completar_generacion`.)
    monkeypatch.setattr(svc, "_build_client", lambda: object())

    # paid_balance=1: este test pide tier="largo" (informe completo), que se
    # cobra del lote paid (RF9), no del free que trae el default del modelo.
    a = Account.objects.create(paid_balance=1)
    otorgar(a, "informe_natal", 1, origen="compra", external_id="test:delete-charts-preserva-ledger")
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    uuid = resp.data["id"]
    resp = _client(a).post(
        f"/api/charts/{uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 202  # Task 10: se cobra sincrónico, se genera en un hilo aparte
    movs_antes = Movimiento.objects.count()
    assert movs_antes > 0
    assert Movimiento.objects.filter(tipo="consumo", codigo_producto="informe_natal").exists()

    assert _client(a).delete("/api/charts/").status_code == 204

    assert Chart.objects.filter(account=a).count() == 0
    assert Movimiento.objects.count() == movs_antes
    # el FK a la carta borrada queda en NULL, no arrastra el movimiento
    assert Movimiento.objects.filter(
        tipo="consumo", codigo_producto="informe_natal", chart__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_delete_account_borra_birth_data():
    """El borrado de cuenta debe llevarse también los datos de nacimiento (dato personal)."""
    a = Account.objects.create()
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert BirthData.objects.count() == 1

    delete_account(a)

    assert BirthData.objects.count() == 0
