import pytest
from django.db import connection

from api import cupo_diario
from api.models import CupoDiario
from tests.api.concurrencia import en_hilos, requiere_postgres

pytestmark = [pytest.mark.django_db(transaction=True), requiere_postgres]


def test_cincuenta_reservas_a_la_vez_con_tope_cuarenta_dan_cuarenta():
    def reservar(_i):
        try:
            return cupo_diario.reservar(cupo_diario.ANONIMO, 40)
        finally:
            connection.close()

    resultados, errores = en_hilos(reservar, 50)
    assert errores == []
    assert sum(1 for r in resultados if r is not None) == 40
    assert CupoDiario.objects.get(ambito="anonimo").usados == 40
