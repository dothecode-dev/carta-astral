"""Pagar tiene que dejar el informe escribiéndose, no un botón de comprar.

El 02-09-2026, con la firma y el monto ya arreglados, el primer pago real se
acreditó bien y aun así la carta seguía ofreciendo "Comprar el informe
completo": el webhook canjeaba el derecho contra la carta —lo consumía— pero
nadie creaba la `Interpretation` ni arrancaba la generación. Quien pagaba
quedaba con el derecho gastado, sin informe, y con un botón que le cobraba de
nuevo.

Lo que se prueba acá es que `order.paid` con una carta atada deja la generación
iniciada. Si el hilo muere, `reanudar_informes` la termina: para eso mira las
`Interpretation` incompletas, y sin esta fila no habría nada que reanudar.
"""

import json

import pytest

from api import interpretation_service as svc
from api.models import Interpretation, PasarelaCheckout
from tests.api.polar_firma import SECRETO
from tests.api.polar_firma import firmar as _firmar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {"prod_uno": "informe_natal", "prod_cinco": "pack_5_natal"}


@pytest.fixture
def sin_hilo(monkeypatch):
    """Registra los arranques en vez de lanzarlos.

    El hilo real llamaría al modelo; lo que este archivo verifica es que el
    webhook lo pida, y que la fila quede creada para que el cron la retome.
    """
    arrancados = []
    monkeypatch.setattr(
        svc, "arrancar_en_hilo",
        lambda interpretacion, chart, account: arrancados.append(interpretacion),
    )
    return arrancados


def _orden(**cambios) -> dict:
    orden = {
        "id": "ord_1", "status": "paid", "paid": True,
        "subtotal_amount": 2900, "discount_amount": 0, "net_amount": 2397,
        "tax_amount": 503, "total_amount": 2900, "currency": "usd",
        "checkout_id": "chk_1", "product_id": "prod_uno",
    }
    orden.update(cambios)
    return orden


def _entregar(client, orden=None):
    body = json.dumps({"type": "order.paid", "data": orden or _orden()}).encode()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json", **_firmar(body),
    )


def test_pagar_desde_una_carta_deja_el_informe_arrancado(
    client, make_account, make_chart, sin_hilo,
):
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
        chart=carta, locale="es",
    )

    _entregar(client)

    interpretacion = Interpretation.objects.filter(chart=carta, lang="es", tier="largo").first()
    assert interpretacion is not None
    assert not interpretacion.completa
    assert sin_hilo == [interpretacion]


def test_el_informe_se_escribe_en_el_idioma_en_que_se_compro(
    client, make_account, make_chart, sin_hilo,
):
    """El idioma sale del checkout, no de un default.

    Quien compra en portugués y cierra la pestaña no tiene después cómo pedir
    el idioma: si el webhook asumiera "es", el informe pago saldría en otro
    idioma y traducirlo sería otro trabajo del modelo.
    """
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
        chart=carta, locale="pt",
    )

    _entregar(client)

    assert Interpretation.objects.filter(chart=carta, lang="pt", tier="largo").exists()


def test_una_compra_sin_carta_no_arranca_nada(client, make_account, sin_hilo):
    """Un informe comprado suelto no sabe sobre qué carta se escribe."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
    )

    _entregar(client)

    assert Interpretation.objects.count() == 0
    assert sin_hilo == []


def test_un_pack_no_arranca_nada(client, make_account, make_chart, sin_hilo):
    """El pack deja cinco informes para usar cuando la persona quiera: elegir
    una carta por ella sería gastarle uno sin que lo pida."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id="chk_5", account=cuenta, codigo_producto="pack_5_natal",
        chart=carta, locale="es",
    )

    _entregar(client, orden=_orden(checkout_id="chk_5", product_id="prod_cinco",
                                   subtotal_amount=12500, total_amount=12500))

    assert Interpretation.objects.count() == 0
    assert sin_hilo == []


def test_si_la_generacion_no_arranca_el_pago_queda_acreditado_igual(
    client, make_account, make_chart, monkeypatch,
):
    """La plata no se pierde porque el arranque falle.

    Responder 4xx o 5xx acá sumaría a las diez entregas fallidas que
    deshabilitan el endpoint para todos los pagos que vengan después, y el
    derecho ya está otorgado: el cron de reanudación no alcanza —no hay fila
    que reanudar—, pero la carta queda pagada y el botón la puede pedir.
    """
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
        chart=carta, locale="es",
    )

    def _explota(*a, **kw):
        raise RuntimeError("el modelo no responde")

    monkeypatch.setattr(svc, "iniciar_generacion", _explota)

    resp = _entregar(client)

    assert 200 <= resp.status_code < 300


def test_en_mantenimiento_la_compra_se_acredita_pero_el_hilo_no_arranca(
    client, make_account, make_chart, sin_hilo,
):
    """Durante un deploy la plata se acredita igual y el informe espera.

    Rechazar la entrega sumaría a las diez fallidas que apagan el endpoint para
    todos los pagos que vengan después. Y arrancar el hilo sería peor: el
    contenedor está por morir y el informe quedaría a medias. La fila queda
    creada a propósito —incompleta— y `reanudar_informes` la termina cuando el
    mantenimiento pase: es exactamente la red que ese cron ya es.
    """
    from api import mantenimiento

    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
        chart=carta, locale="es",
    )
    mantenimiento.activar()

    resp = _entregar(client)

    assert 200 <= resp.status_code < 300
    # El derecho se otorgó y la fila del informe existe, lista para el cron.
    assert Interpretation.objects.filter(chart=carta, lang="es", tier="largo").exists()
    # Pero nadie lanzó el hilo.
    assert sin_hilo == []
