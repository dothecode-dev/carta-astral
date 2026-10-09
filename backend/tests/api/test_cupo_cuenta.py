import pytest
from django.utils import timezone

from api import cupo_diario
from api.sujetos import sujeto_natal
from api import interpretation_service as svc
from api.interpretation_service import SinDerecho
from api.models import CupoDiario

pytestmark = pytest.mark.django_db


def test_la_breve_con_cuenta_reserva_en_el_ambito_cuenta(make_account, make_chart, settings, monkeypatch):
    monkeypatch.setattr(svc, "arrancar_en_hilo", lambda *a, **k: None)
    settings.INTERPRETATION_DAILY_CAP = 5
    cuenta = make_account(lecturas_breves=1)
    carta = make_chart(cuenta)
    svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, "corto")
    fila = CupoDiario.objects.get(fecha=timezone.now().date(), ambito=cupo_diario.CUENTA)
    assert fila.usados == 1


def test_el_cupo_anonimo_lleno_no_frena_a_la_cuenta(make_account, make_chart, settings):
    settings.INTERPRETATION_DAILY_CAP = 5
    CupoDiario.objects.create(fecha=timezone.now().date(), ambito=cupo_diario.ANONIMO, usados=999)
    cuenta = make_account(lecturas_breves=1)
    carta = make_chart(cuenta)
    svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, "corto")  # no lanza CapReached


def test_sin_derecho_devuelve_el_lugar(make_account, make_chart, settings):
    settings.INTERPRETATION_DAILY_CAP = 5
    cuenta = make_account(lecturas_breves=0)
    carta = make_chart(cuenta)
    with pytest.raises(SinDerecho):
        svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, "corto")
    fila = CupoDiario.objects.filter(ambito=cupo_diario.CUENTA).first()
    assert fila is None or fila.usados == 0
