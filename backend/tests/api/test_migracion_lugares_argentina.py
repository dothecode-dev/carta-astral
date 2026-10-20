"""La 0068 junta en «Argentina» los lugares guardados con el nombre viejo de una zona argentina."""

import datetime
import importlib

import pytest
from django.apps import apps

from api import conteo
from api.models import ConteoProcedencia

pytestmark = pytest.mark.django_db

migracion = importlib.import_module("api.migrations.0068_lugares_viejos_de_argentina")


def test_suma_los_viejos_a_argentina_por_dia_y_deja_el_resto():
    hoy = datetime.date(2026, 10, 19)
    ayer = hoy - datetime.timedelta(days=1)
    for fecha, valor, n in ((hoy, "Argentina", 60), (hoy, "Cordoba", 7), (hoy, "Jujuy", 4), (ayer, "Mendoza", 2),
                            (hoy, "Montevideo", 1)):
        ConteoProcedencia.objects.create(fecha=fecha, tipo="lugar", valor=valor, cantidad=n)
    ConteoProcedencia.objects.create(fecha=hoy, tipo="canal", valor="Cordoba", cantidad=9)

    migracion.juntar(apps, None)

    lugares = {(f.fecha, f.valor): f.cantidad for f in ConteoProcedencia.objects.filter(tipo="lugar")}
    assert lugares == {(hoy, "Argentina"): 71, (ayer, "Argentina"): 2, (hoy, "Montevideo"): 1}
    assert ConteoProcedencia.objects.get(tipo="canal").cantidad == 9


def test_la_lista_de_la_migracion_es_la_del_codigo():
    assert set(migracion.VIEJOS) == set(conteo.LUGARES_VIEJOS_DE_ARGENTINA)
