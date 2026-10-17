"""Conteo propio, sin cookies: cuántas cartas se calculan y cuántos pagos se abren por día.

PostHog sólo ve a quien acepta las cookies (el 10..16-10-2026: 135 personas
contra 481 clics de Google Ads). Estos números son el total real, sin datos
personales: una fila por día y evento con un contador."""

import datetime

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from api import conteo
from api.models import ConteoDiario, PasarelaCheckout

pytestmark = pytest.mark.django_db

PREVIEW = "/api/charts/preview/"
DATOS = {"date": "1990-05-10", "time": "14:30", "lat": -34.6, "lng": -58.4}


def _hoy():
    return timezone.now().date()


def test_contar_suma_de_a_uno_por_dia_y_evento():
    conteo.contar("carta_calculada")
    conteo.contar("carta_calculada")
    conteo.contar("checkout_abierto")
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="carta_calculada").cantidad == 2
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="checkout_abierto").cantidad == 1


def test_un_evento_desconocido_no_se_cuenta(caplog):
    conteo.contar("cualquiera")
    assert not ConteoDiario.objects.exists()
    assert "cualquiera" in caplog.text


def test_si_la_base_falla_no_rompe_a_quien_cuenta_ni_su_transaccion(monkeypatch, caplog):
    def explota(*a, **k):
        raise DatabaseError("caída")

    monkeypatch.setattr(ConteoDiario.objects, "get_or_create", explota)
    with transaction.atomic():
        conteo.contar("carta_calculada")
        # La transacción de afuera sigue usable: el fallo quedó en su savepoint.
        assert ConteoDiario.objects.count() == 0
    assert "conteo" in caplog.text


def test_la_vista_previa_cuenta_una_carta_calculada(client):
    assert client.post(PREVIEW, DATOS, content_type="application/json").status_code == 200
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="carta_calculada").cantidad == 1


def test_una_vista_previa_rechazada_no_cuenta(client):
    r = client.post(PREVIEW, {"date": "no"}, content_type="application/json")
    assert r.status_code == 400
    assert not ConteoDiario.objects.exists()


def test_el_resumen_trae_los_dias_y_las_compras_pagas():
    ayer = _hoy() - datetime.timedelta(days=1)
    ConteoDiario.objects.create(fecha=_hoy(), evento="carta_calculada", cantidad=7)
    ConteoDiario.objects.create(fecha=ayer, evento="carta_calculada", cantidad=3)
    ConteoDiario.objects.create(fecha=ayer, evento="checkout_abierto", cantidad=1)
    ahora = timezone.now()
    PasarelaCheckout.objects.create(checkout_id="cs_1", codigo_producto="informe_natal", acreditado_at=ahora)
    # Un canje con cupón del 100 % no es una compra paga.
    PasarelaCheckout.objects.create(checkout_id="cupon_x", codigo_producto="informe_natal", acreditado_at=ahora)
    PasarelaCheckout.objects.create(checkout_id="cs_2", codigo_producto="informe_natal")

    r = conteo.resumen(dias=7)

    assert r["total"] == {"carta_calculada": 10, "checkout_abierto": 1, "compra_pagada": 1}
    assert r["por_dia"][str(_hoy())]["carta_calculada"] == 7
    assert r["por_dia"][str(ayer)] == {"carta_calculada": 3, "checkout_abierto": 1, "compra_pagada": 0}
