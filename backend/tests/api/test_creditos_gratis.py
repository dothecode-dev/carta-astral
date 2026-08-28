import pytest
from django.conf import settings

from api.models import Account

pytestmark = pytest.mark.django_db


def test_una_cuenta_nueva_nace_con_tres_gratis():
    # El gratis es el gancho para mostrárselo a otra persona: con uno solo, el
    # dueño ya lo gastó en su propia carta.
    assert Account.objects.create(email="x@y.z").free_balance == 3


def test_el_cap_diario_acota_el_gasto_al_costo_nuevo():
    # Un informe cuesta ~US$0,45, no ~US$0,03: con el cap viejo (500) el techo
    # de regalo pasaba de US$15 a más de US$200 por día.
    assert settings.INTERPRETATION_DAILY_CAP * 0.45 <= 20
