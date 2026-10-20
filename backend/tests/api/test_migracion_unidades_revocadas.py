"""La 0057 completa `unidades_revocadas` en las compras con reembolsos previos."""

import importlib

import pytest
from django.apps import apps

from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db

migracion = importlib.import_module("api.migrations.0057_unidades_revocadas_existentes")


def _fila(checkout_id, codigo, precio, reembolsado, descuento=0):
    return PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id=checkout_id, codigo_producto=codigo, precio_centavos=precio,
        descuento_centavos=descuento, reembolsado_centavos=reembolsado,
    )


def test_completa_total_parcial_regalo_y_sin_reembolso():
    total = _fila("cs_t", "informe_natal", 500, 500)
    parcial_pack = _fila("cs_p", "pack_5_natal", 12500, 2600)  # ceil(1,04) = 2
    regalo = _fila("cs_r", "pack_5_natal", 12500, 0, descuento=12500)
    sin = _fila("cs_s", "informe_natal", 500, 0)

    migracion.completar(apps, None)

    valores = {f.checkout_id: f.unidades_revocadas for f in PasarelaCheckout.objects.all()}
    assert valores == {total.checkout_id: 1, parcial_pack.checkout_id: 2, regalo.checkout_id: 0, sin.checkout_id: 0}


def test_0059_deja_constancia_de_los_reembolsos_viejos(make_account):
    from api.canje import aplicar_compra, revocar
    from api.models import Reembolso

    cuenta = make_account()
    aplicar_compra(cuenta, "informe_natal", 500, external_id="stripe:session:cs_v", precio_centavos=500)
    revocar(cuenta, "informe_natal", 1, external_id="stripe:refund:re_viejo")
    Reembolso.objects.all().delete()

    importlib.import_module("api.migrations.0059_reembolsos_existentes").completar(apps, None)

    assert list(Reembolso.objects.values_list("refund_id", flat=True)) == ["re_viejo"]


def test_un_reembolso_viejo_reentregado_no_se_aplica_de_nuevo(client, settings, make_account):
    """Con la constancia rellenada, la reentrega de un reembolso de antes no
    vuelve a anotar el monto."""
    import json

    from django.utils import timezone

    from api.models import Reembolso
    from tests.api.stripe_firma import SECRETO, firmar

    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    cuenta = make_account()
    fila = PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_v", account=cuenta, codigo_producto="informe_natal", precio_centavos=500,
        pago_id="pi_v", acreditado_at=timezone.now(), reembolsado_centavos=500, unidades_revocadas=1,
    )
    Reembolso.objects.create(refund_id="re_viejo", monto=0)
    obj = {"id": "re_viejo", "amount": 500, "currency": "usd", "payment_intent": "pi_v"}
    cuerpo = json.dumps({"id": "evt", "type": "refund.created", "data": {"object": obj}}).encode()
    client.post("/api/webhooks/stripe/", data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    fila.refresh_from_db()
    assert fila.reembolsado_centavos == 500
