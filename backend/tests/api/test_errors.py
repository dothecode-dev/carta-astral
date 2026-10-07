import pytest

pytestmark = pytest.mark.django_db


def test_missing_required_field_returns_400(account_client):
    resp = account_client.post("/api/charts/", {"date": "1989-07-14"}, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_ocean_coords_return_400(account_client):
    resp = account_client.post("/api/charts/", {
        "date": "1989-07-14", "time": "12:00", "time_known": True,
        "lat": 0.0, "lng": -30.0,
    }, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_campo_faltante_dice_cual_falta_y_no_loguea_el_traceback(account_client, caplog):
    """Antes respondía `"'date'"` (el repr del `KeyError`) y logueaba con
    `exc_info`, que adjunta las variables locales —los datos de nacimiento—."""
    import logging

    with caplog.at_level(logging.WARNING):
        resp = account_client.post("/api/charts/", {"date": "1989-07-14"}, format="json")
    assert resp.status_code == 400
    assert resp.data["error"].startswith("falta el campo ")
    assert "'" not in resp.data["error"]
    rechazos = [r for r in caplog.records if "rechazad" in r.getMessage() or "rejected" in r.getMessage()]
    assert rechazos and all(r.exc_info is None for r in rechazos)
