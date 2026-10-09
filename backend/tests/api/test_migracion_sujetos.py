"""La 0039: cada carta con su sujeto natal, y cada fila con el suyo. PLATA:
un consumo sin sujeto es un informe que se podría cobrar dos veces.

Se ejercita la función `rellenar` con el registro de modelos actual: en el
deploy 1 los dos campos conviven, así que es el mismo esquema que ve la
migración cuando corre."""

import importlib

import pytest
from django.apps import apps

from api.models import Interpretation, Movimiento, PasarelaCheckout, Sujeto
from api.sujetos import sujeto_natal
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

rellenar = importlib.import_module("api.migrations.0039_rellenar_sujetos").rellenar


def _sin_sujetos():
    """El estado previo a la migración: nada tiene sujeto."""
    Interpretation.objects.update(sujeto=None)
    Movimiento.objects.update(sujeto=None)
    PasarelaCheckout.objects.update(sujeto=None)
    Sujeto.objects.all().delete()


def test_cada_carta_y_cada_fila_quedan_con_su_sujeto(make_chart, account):
    c1, c2 = make_chart(account=account), make_chart(account=account)
    Interpretation.objects.create(sujeto=sujeto_natal(c1), chart=c1, lang="es", prompt_version=PROMPT_VERSION, text="")
    Movimiento.objects.create(
        account=account, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=c2,
    )
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account, codigo_producto="informe_natal", sujeto=sujeto_natal(c2), chart=c2,
    )
    _sin_sujetos()

    conteo = rellenar(apps)

    assert Sujeto.objects.filter(producto="natal").count() == 2
    assert not Interpretation.objects.filter(sujeto__isnull=True).exists()
    assert Movimiento.objects.get(chart=c2).sujeto.natal_de_id == c2.pk
    assert PasarelaCheckout.objects.get(checkout_id="cs_1").sujeto.natal_de_id == c2.pk
    assert conteo["sujetos"] == 2


def test_lo_que_no_tiene_carta_sigue_sin_sujeto(account):
    # El fixture `account` ya deja sus propios movimientos (el regalo de la
    # lectura breve): se mira la fila que crea este test, no "la única".
    otorgamiento = Movimiento.objects.create(
        account=account, codigo_producto="informe_natal", tipo="otorgamiento",
        origen="compra", cantidad=1,
    )
    pack = PasarelaCheckout.objects.create(
        checkout_id="cs_p", account=account, codigo_producto="pack_3_natal",
    )
    _sin_sujetos()

    rellenar(apps)

    assert Movimiento.objects.get(pk=otorgamiento.pk).sujeto_id is None
    assert PasarelaCheckout.objects.get(pk=pack.pk).sujeto_id is None
    assert not Movimiento.objects.filter(chart__isnull=True, sujeto__isnull=False).exists()


def test_correrla_dos_veces_no_duplica_nada(make_chart, account):
    """El deploy 2 la vuelve a correr para lo que escribió el código viejo."""
    c = make_chart(account=account)
    Interpretation.objects.create(sujeto=sujeto_natal(c), chart=c, lang="es", prompt_version=PROMPT_VERSION, text="")
    _sin_sujetos()

    rellenar(apps)
    rellenar(apps)

    assert Sujeto.objects.count() == 1
    assert Interpretation.objects.get().sujeto.natal_de_id == c.pk


def test_respeta_un_sujeto_que_ya_estaba(make_chart, account):
    c = make_chart(account=account)
    previo = Sujeto.objects.create(producto="natal", natal_de=c)

    rellenar(apps)

    assert Sujeto.objects.get().pk == previo.pk
