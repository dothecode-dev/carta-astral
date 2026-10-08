import pytest
from django.db import connection

from api import lectura_anonima as la
from tests.api.concurrencia import en_hilos, requiere_postgres

pytestmark = [pytest.mark.django_db(transaction=True), requiere_postgres]


def test_diez_a_la_vez_con_concurrencia_tres_toman_tres_slots(db_cache, settings):
    settings.LECTURA_ANONIMA_CONCURRENCIA = 3

    def tomar(i):
        try:
            return la._tomar_slot(f"h{i}")
        finally:
            connection.close()

    resultados, errores = en_hilos(tomar, 10)
    assert errores == []
    assert sorted(r for r in resultados if r is not None) == [0, 1, 2]
