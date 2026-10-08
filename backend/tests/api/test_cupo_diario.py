import pytest

from api import cupo_diario
from api.models import CupoDiario

pytestmark = pytest.mark.django_db


def test_reserva_hasta_el_tope_y_despues_no():
    fechas = [cupo_diario.reservar(cupo_diario.ANONIMO, 2) for _ in range(3)]
    assert fechas[0] is not None and fechas[1] is not None
    assert fechas[2] is None
    assert CupoDiario.objects.get(ambito="anonimo").usados == 2


def test_los_ambitos_no_se_tocan():
    assert cupo_diario.reservar(cupo_diario.ANONIMO, 1) is not None
    assert cupo_diario.reservar(cupo_diario.ANONIMO, 1) is None
    assert cupo_diario.reservar(cupo_diario.CUENTA, 1) is not None


def test_devolver_libera_un_lugar_y_nunca_baja_de_cero():
    fecha = cupo_diario.reservar(cupo_diario.ANONIMO, 1)
    cupo_diario.devolver(cupo_diario.ANONIMO, fecha)
    cupo_diario.devolver(cupo_diario.ANONIMO, fecha)
    assert CupoDiario.objects.get(ambito="anonimo").usados == 0
    assert cupo_diario.reservar(cupo_diario.ANONIMO, 1) is not None
