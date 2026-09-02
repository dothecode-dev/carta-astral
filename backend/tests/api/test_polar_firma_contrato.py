"""El contrato de firma con Polar, anclado a una fuente que no somos nosotros.

Este archivo existe por un fallo concreto: el 02-09-2026 el primer pago real de
prueba llegó al webhook y se rechazó con 403, con la suite entera en verde. La
causa era que verificábamos la firma derivando la clave de una forma que Polar
no usa, y los tests firmaban con esa misma derivación equivocada: se validaban
contra sí mismos.

Por eso acá el árbitro es el verificador oficial de Polar (`polar_sdk`, sólo
dependencia de desarrollo: no entra en la imagen de producción). Si Polar
cambiara la forma de firmar, al actualizar el SDK estos tests se ponen rojos.

Que el SDK acepte una firma nuestra prueba que derivamos la misma clave que
Polar usa para firmar: el HMAC es simétrico, y `validate_event` es literalmente
el código con el que Polar te dice que verifiques sus entregas.

Lo que se ancla acá es SÓLO la firma. `validate_event` además parsea la orden
entera contra los modelos pydantic del SDK y levanta si falta cualquier campo
—se comprobó escribiendo este test, con 34 errores de validación sobre un
payload mínimo—: es exactamente la razón por la que el SDK no va en el camino
de producción, donde un campo nuevo de Polar nos haría fallar la entrega de un
pago.
"""

import json

import pytest
from polar_sdk.webhooks import WebhookVerificationError, validate_event

from api.models import Derecho, Movimiento
from tests.api.polar_firma import SECRETO, firmar, firmar_a_la_vieja

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {"prod_uno": "informe_natal"}


def _cuerpo() -> bytes:
    return json.dumps(
        {
            "type": "order.paid",
            "data": {
                "id": "ord_1",
                "checkout_id": "chk_1",
                "product_id": "prod_uno",
                "net_amount": 2900,
            },
        }
    ).encode()


def _la_firma_convence_al_sdk_de_polar(body: bytes, cabeceras: dict[str, str]) -> bool:
    """Si el verificador oficial da por buena la firma de estas cabeceras.

    Sólo mira la firma: un `ValidationError` de pydantic significa que la firma
    YA pasó y lo que falló después fue el parseo del payload, que a este test
    no le incumbe.
    """
    headers = {
        "webhook-id": cabeceras["HTTP_WEBHOOK_ID"],
        "webhook-timestamp": cabeceras["HTTP_WEBHOOK_TIMESTAMP"],
        "webhook-signature": cabeceras["HTTP_WEBHOOK_SIGNATURE"],
    }
    try:
        validate_event(body, headers, SECRETO)
    except WebhookVerificationError:
        return False
    except Exception:
        # Parseo, no firma.
        return True
    return True


def test_el_verificador_oficial_de_polar_acepta_nuestra_firma():
    """El ancla: si esto pasa, firmamos con la misma clave que deriva Polar.

    Al SDK se le pasa el secreto crudo —él hace el base64 por dentro—, que es
    exactamente la diferencia que nos costó el 403.
    """
    body = _cuerpo()

    assert _la_firma_convence_al_sdk_de_polar(body, firmar(body))


def test_el_verificador_oficial_rechaza_la_derivacion_que_teniamos():
    """La otra mitad del ancla: la forma vieja no es la de Polar.

    Sin este test, `firmar` y `firmar_a_la_vieja` podrían volverse lo mismo sin
    que nadie se entere, y el de arriba pasaría por casualidad.
    """
    body = _cuerpo()

    assert not _la_firma_convence_al_sdk_de_polar(body, firmar_a_la_vieja(body))


def test_nuestro_endpoint_acepta_una_entrega_firmada_como_las_de_polar(client):
    """El caso que fallaba en producción con un pago de verdad."""
    body = _cuerpo()

    resp = client.post(
        "/api/webhooks/polar/", body, content_type="application/json", **firmar(body),
    )

    assert 200 <= resp.status_code < 300


def test_nuestro_endpoint_rechaza_una_firma_hecha_a_la_vieja(client):
    """Volver a la derivación vieja tiene que costar un test en rojo, no un
    403 silencioso en producción tres semanas después."""
    body = _cuerpo()

    resp = client.post(
        "/api/webhooks/polar/", body, content_type="application/json",
        **firmar_a_la_vieja(body),
    )

    assert resp.status_code == 403
    assert Movimiento.objects.count() == 0
    assert Derecho.objects.count() == 0
