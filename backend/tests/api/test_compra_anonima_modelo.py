import pytest
from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db


def test_una_fila_nueva_no_es_anonima_por_defecto(make_account):
    f = PasarelaCheckout.objects.create(checkout_id="cs_x", account=make_account(), codigo_producto="informe_natal")
    assert (f.anonimo, f.nonce_hash, f.cuenta_nueva, f.canjeado_at) == (False, "", False, None)
