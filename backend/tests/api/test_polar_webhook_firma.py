"""Lo primero que hace el webhook es no confiar en quien le habla.

La URL es pública y sin autenticación de sesión: lo único que separa un pago
real de uno inventado es la firma. Por eso se verifica ANTES de mirar el
contenido — un payload que no está firmado no merece ni que lo parseemos.

Standard Webhooks: headers `webhook-id`, `webhook-timestamp` y
`webhook-signature`, HMAC-SHA256 sobre `id.timestamp.body`, con tolerancia de
±5 minutos para que un replay de ayer no acredite nada.
"""

import base64
import json
import time

import pytest
from django.urls import resolve

from api.models import Derecho, Movimiento
from api.webhooks_polar import PolarWebhookView
from tests.api.polar_firma import SECRETO
from tests.api.polar_firma import firmar as _firmar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {"prod_uno": "informe_natal"}


def _cuerpo(tipo="order.paid") -> bytes:
    return json.dumps({"type": tipo, "data": {"id": "ord_1"}}).encode()


def _entregar(client, body=None, secreto=SECRETO, **kw):
    body = body or _cuerpo()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json",
        **_firmar(body, secreto, **kw),
    )


def test_la_ruta_termina_en_barra():
    """Polar no sigue redirects: sin la barra, APPEND_SLASH responde 301 y la
    entrega cuenta como fallida. Diez fallidas seguidas y Polar deshabilita el
    endpoint — es el bug del commit 839ba19, que ya nos pasó con RevenueCat."""
    assert resolve("/api/webhooks/polar/").func.view_class is PolarWebhookView


def test_una_firma_de_otro_secreto_es_403_y_no_mueve_nada(client):
    otro = "whsec_" + base64.b64encode(b"otro-secreto-distinto-de-32-byte").decode()

    resp = _entregar(client, secreto=otro)

    assert resp.status_code == 403
    assert Movimiento.objects.count() == 0
    assert Derecho.objects.count() == 0


def test_un_cuerpo_modificado_despues_de_firmar_es_403(client):
    """La firma cubre el body: cambiarle un byte al payload la invalida."""
    body = _cuerpo()
    cabeceras = _firmar(body, SECRETO)

    resp = client.post(
        "/api/webhooks/polar/", body.replace(b"ord_1", b"ord_9"),
        content_type="application/json", **cabeceras,
    )

    assert resp.status_code == 403


def test_un_timestamp_viejo_es_403(client):
    """Tolerancia ±5 minutos: un replay de ayer, con su firma válida y todo,
    no acredita."""
    viejo = str(int(time.time()) - 3600)

    assert _entregar(client, ts=viejo).status_code == 403


def test_sin_secreto_configurado_es_403(client, settings):
    """Fail-closed, igual que el webhook de RevenueCat: sin con qué verificar,
    no se confía en nadie. Lo contrario —aceptar todo cuando falta la
    configuración— es la peor forma de fallar en un endpoint de plata."""
    settings.POLAR_WEBHOOK_SECRET = ""

    assert _entregar(client).status_code == 403


def test_una_firma_valida_pasa(client):
    """El caso feliz de esta tarea: la firma se acepta. Qué se hace con el
    evento es la tarea siguiente."""
    resp = _entregar(client)

    assert 200 <= resp.status_code < 300


def test_sin_cabeceras_de_firma_es_403(client):
    resp = client.post("/api/webhooks/polar/", _cuerpo(), content_type="application/json")

    assert resp.status_code == 403


def test_un_evento_que_no_escuchamos_responde_2xx(client):
    """`order.created` llega con la orden en pending. No acredita nada, pero
    responde 2xx: un 4xx acá suma a las diez entregas fallidas que
    deshabilitan el endpoint para todos los demás eventos."""
    resp = _entregar(client, body=_cuerpo("order.created"))

    assert 200 <= resp.status_code < 300
    assert Movimiento.objects.count() == 0
