"""La firma es la única autenticación del webhook: tests 1-5 de la spec.

La URL es pública. Sin verificación de firma, cualquiera acredita informes.
"""

import json

import pytest

from api.models import Derecho, Movimiento
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"


def _cuerpo(tipo: str = "checkout.session.completed") -> bytes:
    return json.dumps({
        "id": "evt_1", "type": tipo,
        "data": {"object": {"id": "cs_test_1", "object": "checkout.session"}},
    }).encode()


def _postear(client, cuerpo: bytes, firma: str | None):
    cabeceras = {"HTTP_STRIPE_SIGNATURE": firma} if firma is not None else {}
    return client.post(URL, data=cuerpo, content_type="application/json", **cabeceras)


def test_sin_secreto_configurado_rechaza_y_no_toca_la_base(client, settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    cuerpo = _cuerpo()

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert r.status_code == 403
    assert not Movimiento.objects.exists()
    assert not Derecho.objects.exists()


def test_una_firma_invalida_se_rechaza(client, settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO

    r = _postear(client, _cuerpo(), "t=1,v1=" + "0" * 64)

    assert r.status_code == 403


def test_sin_el_header_de_firma_se_rechaza(client, settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO

    r = _postear(client, _cuerpo(), None)

    assert r.status_code == 403


def test_una_firma_armada_como_dice_la_documentacion_pasa(client, settings):
    """Ancla el contrato: firmamos con el algoritmo público y verifica la
    librería oficial. Si divergen, esto se pone rojo."""
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    cuerpo = _cuerpo("payment_intent.created")  # un evento que no escuchamos

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert r.status_code == 200


def test_un_timestamp_fuera_de_tolerancia_se_rechaza(client, settings):
    """El replay de una entrega vieja no vale, aunque la firma sea buena."""
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    cuerpo = _cuerpo()

    r = _postear(client, cuerpo, firmar(cuerpo, timestamp=1_600_000_000))

    assert r.status_code == 403


def test_un_evento_que_no_escuchamos_no_mueve_nada(client, settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    cuerpo = _cuerpo("customer.created")

    r = _postear(client, cuerpo, firmar(cuerpo))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()
    assert not Derecho.objects.exists()
