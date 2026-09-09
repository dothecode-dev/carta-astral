"""El webhook de rebotes de Resend (RF15): deja rastro de un código de
acceso que no llegó. No acredita ni escribe nada en la base —a diferencia
del de Stripe—, así que estos tests miran la respuesta y el log, nada más.
"""

import json
import logging

import pytest

from tests.api.resend_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/resend/"

EMAIL_ID = "56761188-7520-42d8-8898-ff6fc54ce618"
DIRECCION = "filtrar-esto@example.com"


def _cuerpo(tipo: str = "email.bounced") -> bytes:
    payload = {
        "type": tipo,
        "created_at": "2026-09-09T12:00:00.000Z",
        "data": {
            "email_id": EMAIL_ID,
            "from": "ASTRA <info@astraguia.com>",
            "to": [DIRECCION],
            "subject": "Tu código de acceso",
        },
    }
    return json.dumps(payload).encode()


def _cabeceras_django(cabeceras: dict[str, str] | None) -> dict:
    if not cabeceras:
        return {}
    return {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in cabeceras.items()}


def _postear(client, cuerpo: bytes, cabeceras: dict[str, str] | None):
    return client.post(
        URL, data=cuerpo, content_type="application/json", **_cabeceras_django(cabeceras),
    )


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.RESEND_WEBHOOK_SECRET = SECRETO


def test_un_rebote_con_firma_valida_devuelve_2xx_y_queda_logueado(client, caplog):
    caplog.set_level(logging.INFO)
    cuerpo = _cuerpo("email.bounced")

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert 200 <= r.status_code < 300
    logueados = [rec for rec in caplog.records if getattr(rec, "resend_id", None) == EMAIL_ID]
    assert logueados
    assert logueados[0].levelno == logging.ERROR
    assert getattr(logueados[0], "tipo_evento", None) == "email.bounced"


def test_una_queja_con_firma_valida_devuelve_2xx_y_queda_logueada(client, caplog):
    caplog.set_level(logging.INFO)
    cuerpo = _cuerpo("email.complained")

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert 200 <= r.status_code < 300
    logueados = [rec for rec in caplog.records if getattr(rec, "resend_id", None) == EMAIL_ID]
    assert logueados
    assert getattr(logueados[0], "tipo_evento", None) == "email.complained"


def test_sin_firma_se_rechaza(client):
    r = _postear(client, _cuerpo(), None)

    assert r.status_code == 403


def test_con_una_firma_que_no_corresponde_se_rechaza(client):
    """Firmada con un secreto distinto del configurado."""
    cuerpo = _cuerpo()
    otro_secreto = "whsec_" + "a" * 44

    r = _postear(client, cuerpo, firmar(cuerpo, secreto=otro_secreto))

    assert r.status_code == 403


def test_con_el_timestamp_viejo_se_rechaza(client):
    """El ataque de reenvío: firma válida, pero de una entrega vieja."""
    cuerpo = _cuerpo()

    r = _postear(client, cuerpo, firmar(cuerpo, timestamp=1_600_000_000))

    assert r.status_code == 403


def test_sin_secreto_configurado_rechaza_todo_aunque_la_firma_venga_bien(client, settings, caplog):
    caplog.set_level(logging.INFO)
    settings.RESEND_WEBHOOK_SECRET = ""
    cuerpo = _cuerpo()

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert r.status_code == 403
    assert not any(getattr(rec, "resend_id", None) == EMAIL_ID for rec in caplog.records)


def test_el_log_no_incluye_la_direccion(client, caplog):
    caplog.set_level(logging.INFO)
    cuerpo = _cuerpo("email.bounced")

    _postear(client, cuerpo, firmar(cuerpo))

    assert caplog.records
    for rec in caplog.records:
        assert DIRECCION not in rec.getMessage()
        assert DIRECCION not in str(rec.__dict__)


def test_un_evento_que_no_nos_interesa_no_explota_y_no_ensucia_el_log(client, caplog):
    caplog.set_level(logging.INFO)
    cuerpo = _cuerpo("email.delivered")

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert 200 <= r.status_code < 300
    assert not any(rec.levelno >= logging.ERROR for rec in caplog.records)
