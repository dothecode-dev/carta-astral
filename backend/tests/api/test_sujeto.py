"""El sujeto de un informe pago (parte 2 de la spec de Vínculo, RF5-RF6).

Superficie de PLATA: la idempotencia del cobro pasa a ser por sujeto, así que
dos sujetos natales para la misma carta permitirían canjear el mismo informe
dos veces. Por eso la unicidad la pone la base, no el código."""

import pytest
from django.db import IntegrityError, transaction

from api.models import Interpretation, Movimiento, PasarelaCheckout, Sujeto
from api.sujetos import a_sujeto, adoptar_huerfanas, sujeto_natal
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db


def test_sujeto_natal_se_crea_una_sola_vez(chart):
    primero = sujeto_natal(chart)
    segundo = sujeto_natal(chart)
    assert primero.pk == segundo.pk
    assert primero.producto == Sujeto.NATAL
    assert primero.natal_de_id == chart.pk
    assert primero.account_id == chart.account_id
    assert Sujeto.objects.filter(natal_de=chart).count() == 1


def test_la_base_impide_dos_sujetos_natales_para_la_misma_carta(chart):
    sujeto_natal(chart)
    with pytest.raises(IntegrityError), transaction.atomic():
        Sujeto.objects.create(producto=Sujeto.NATAL, natal_de=chart)


def test_si_otro_proceso_lo_creo_primero_devuelve_ese(chart, monkeypatch):
    """La carrera: entre el `filter` y el `create`, otro proceso lo creó."""
    ganador = Sujeto.objects.create(producto=Sujeto.NATAL, natal_de=chart)
    real_filter = Sujeto.objects.filter

    llamadas = {"n": 0}

    def filter_que_llega_tarde(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return Sujeto.objects.none()  # simula que todavía no existía
        return real_filter(*args, **kwargs)

    monkeypatch.setattr(Sujeto.objects, "filter", filter_que_llega_tarde)
    assert sujeto_natal(chart).pk == ganador.pk


def test_un_natal_tiene_carta_y_un_vinculo_no(chart):
    with pytest.raises(IntegrityError), transaction.atomic():
        Sujeto.objects.create(producto=Sujeto.NATAL, natal_de=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        Sujeto.objects.create(producto=Sujeto.VINCULO, natal_de=chart)
    assert Sujeto.objects.create(producto=Sujeto.VINCULO).natal_de is None


def test_crear_una_carta_crea_su_sujeto_natal(account):
    from api.chart_service import create_chart

    carta = create_chart(
        {"date": "1976-05-31", "time": "19:30", "lat": -34.5, "lng": -58.5}, account,
    )
    assert carta.sujeto_natal.producto == Sujeto.NATAL


def test_a_sujeto_acepta_carta_o_sujeto_y_rechaza_otra_cosa(chart):
    s = sujeto_natal(chart)
    assert a_sujeto(chart).pk == s.pk
    assert a_sujeto(s).pk == s.pk
    with pytest.raises(TypeError):
        a_sujeto("una carta")


def test_una_interpretacion_escrita_con_carta_sale_con_su_sujeto(chart, account):
    """EXPANDIR: mientras conviven los dos campos, toda fila nueva con carta
    lleva el sujeto. Así ningún test ni llamador existente tiene que cambiar."""
    i = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    assert i.sujeto_id == sujeto_natal(chart).pk


def test_un_checkout_con_carta_sale_con_su_sujeto_y_sin_carta_sin_sujeto(chart, account):
    con = PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account, codigo_producto="informe_natal", chart=chart,
    )
    sin = PasarelaCheckout.objects.create(
        checkout_id="cs_2", account=account, codigo_producto="informe_natal",
    )
    assert con.sujeto_id == sujeto_natal(chart).pk
    assert sin.sujeto_id is None


def test_adopta_las_filas_huerfanas_de_su_carta(chart, account):
    """Lo que escribió el código viejo durante el deploy llega sin sujeto."""
    i = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    m = Movimiento.objects.create(
        account=account, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=chart,
    )
    p = PasarelaCheckout.objects.create(
        checkout_id="cs_3", account=account, codigo_producto="informe_natal", chart=chart,
    )
    Interpretation.objects.filter(pk=i.pk).update(sujeto=None)
    PasarelaCheckout.objects.filter(pk=p.pk).update(sujeto=None)

    s = sujeto_natal(chart)
    adoptar_huerfanas(s)

    for modelo, pk in ((Interpretation, i.pk), (Movimiento, m.pk), (PasarelaCheckout, p.pk)):
        assert modelo.objects.get(pk=pk).sujeto_id == s.pk, modelo.__name__


def test_adoptar_no_toca_filas_de_otra_carta(make_chart, account):
    una, otra = make_chart(account=account), make_chart(account=account)
    m = Movimiento.objects.create(
        account=account, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=otra,
    )
    adoptar_huerfanas(sujeto_natal(una))
    assert Movimiento.objects.get(pk=m.pk).sujeto_id is None


def test_borrar_la_carta_borra_su_sujeto_natal_y_el_informe(chart, account):
    """Mismo efecto que hoy: el informe cae con la carta (CASCADE)."""
    i = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    chart.delete()
    assert not Sujeto.objects.exists()
    assert not Interpretation.objects.filter(pk=i.pk).exists()
