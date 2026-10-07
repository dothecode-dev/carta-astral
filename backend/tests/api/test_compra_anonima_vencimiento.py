"""RF8: lo que no se paga se borra. `checkout.session.expired` sobre una
compra sin cuenta descarta la carta, su BirthData y su sujeto natal; una
fila con cuenta o acreditada no pierde nada."""

import pytest
from django.utils import timezone

from api import compra_anonima
from api.models import BirthData, Chart, PasarelaCheckout, Sujeto
from tests.api.conftest import SESSION_ANONIMA, sesion_anonima

pytestmark = pytest.mark.django_db

EXPIRED = "checkout.session.expired"


def test_vencida_sin_pagar_borra_la_carta_anonima(entregar_anonima, anonima):
    carta_id, bd_id = anonima.chart_id, anonima.chart.birth_data_id
    assert Sujeto.objects.filter(natal_de_id=carta_id).exists()

    assert entregar_anonima(sesion_anonima(), tipo=EXPIRED).status_code == 200

    assert not Chart.objects.filter(pk=carta_id).exists()
    assert not BirthData.objects.filter(pk=bd_id).exists()
    assert not Sujeto.objects.filter(natal_de_id=carta_id).exists()
    anonima.refresh_from_db()
    assert anonima.vencido_at is not None
    assert anonima.chart_id is None and anonima.sujeto_id is None


def test_el_mismo_evento_dos_veces_es_idempotente(entregar_anonima, anonima):
    entregar_anonima(sesion_anonima(), tipo=EXPIRED)
    assert entregar_anonima(sesion_anonima(), tipo=EXPIRED).status_code == 200
    assert compra_anonima.descartar(SESSION_ANONIMA) is False


def test_vencida_con_cuenta_no_borra_nada(entregar_anonima, anonima, make_account):
    """Adjudicada pero sin acreditar (el acreditado falló y hay reintento
    pendiente): la carta es de alguien y no se toca."""
    anonima.account = make_account()
    anonima.save()
    carta_id = anonima.chart_id

    entregar_anonima(sesion_anonima(), tipo=EXPIRED)

    assert Chart.objects.filter(pk=carta_id).exists()
    anonima.refresh_from_db()
    assert anonima.chart_id == carta_id


def test_acreditada_no_se_borra_aunque_llegue_expired(entregar_anonima, anonima):
    anonima.acreditado_at = timezone.now()
    anonima.save()
    carta_id = anonima.chart_id

    entregar_anonima(sesion_anonima(), tipo=EXPIRED)

    assert Chart.objects.filter(pk=carta_id).exists()
    assert Sujeto.objects.filter(natal_de_id=carta_id).exists()
    anonima.refresh_from_db()
    assert anonima.chart_id == carta_id


def test_una_fila_con_cuenta_no_anonima_no_se_descarta(make_account, make_chart):
    cuenta = make_account()
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_con_cuenta", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    assert compra_anonima.descartar("cs_con_cuenta") is False
    assert Chart.objects.filter(pk=fila.chart_id).exists()


def test_el_birth_data_se_conserva_si_otra_carta_lo_usa(anonima):
    bd = anonima.chart.birth_data
    otra = Chart.objects.create(birth_data=bd, data={}, engine_version="test")

    assert compra_anonima.descartar(SESSION_ANONIMA) is True

    assert BirthData.objects.filter(pk=bd.pk).exists()
    assert Chart.objects.filter(pk=otra.pk).exists()


def test_sin_fila_devuelve_false():
    assert compra_anonima.descartar("cs_inexistente") is False


# --- `checkout.session.async_payment_failed` (revisión final, Important 2) ---
#
# Con Managed Payments un medio asincrónico que falla deja la sesión
# `complete`: nunca llega `expired`. Sin este evento la carta anónima quedaba
# guardada para siempre, contra la política de privacidad.

FAILED = "checkout.session.async_payment_failed"


def test_pago_asincronico_fallido_borra_la_carta_anonima(entregar_anonima, anonima):
    carta_id, bd_id = anonima.chart_id, anonima.chart.birth_data_id

    assert entregar_anonima(sesion_anonima(payment_status="unpaid"), tipo=FAILED).status_code == 200

    assert not Chart.objects.filter(pk=carta_id).exists()
    assert not BirthData.objects.filter(pk=bd_id).exists()
    anonima.refresh_from_db()
    assert anonima.vencido_at is not None
    assert anonima.chart_id is None


def test_pago_asincronico_fallido_con_cuenta_no_borra_nada(entregar_anonima, make_account, make_chart):
    """Checkout abierto CON cuenta: la carta es de la cuenta y no se toca;
    la fila sólo deja de ser un pago en curso, igual que con `expired`."""
    from tests.api.conftest import SESSION_ANONIMA as SID

    cuenta = make_account()
    carta = make_chart(account=cuenta)
    fila = PasarelaCheckout.objects.create(
        checkout_id=SID, account=cuenta, codigo_producto="informe_natal", chart=carta,
    )

    assert entregar_anonima(sesion_anonima(payment_status="unpaid"), tipo=FAILED).status_code == 200

    assert Chart.objects.filter(pk=carta.pk).exists()
    fila.refresh_from_db()
    assert fila.chart_id == carta.pk and fila.account_id == cuenta.pk
    assert fila.acreditado_at is None


def test_pago_asincronico_fallido_no_toca_una_fila_acreditada(entregar_anonima, anonima):
    anonima.acreditado_at = timezone.now()
    anonima.save()
    carta_id = anonima.chart_id

    entregar_anonima(sesion_anonima(), tipo=FAILED)

    assert Chart.objects.filter(pk=carta_id).exists()
    anonima.refresh_from_db()
    assert anonima.chart_id == carta_id and anonima.vencido_at is None
