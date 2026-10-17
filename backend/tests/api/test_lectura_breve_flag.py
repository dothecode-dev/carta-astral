"""`LECTURA_BREVE_GRATIS_ENABLED`: el flag que apaga la breve gratis por IA.

Apaga las dos puertas por las que la breve sale gratis —la lectura anónima y
el regalo de bienvenida de una cuenta nueva— sin tocar lo ya otorgado: un
derecho `lectura_breve` que existe se sigue canjeando. Superficie crítica
(cuentas, ledger, tombstone): estos tests corren también contra Postgres.
"""
import pytest
from rest_framework.test import APIClient

from api import lectura_anonima as la
from api.accounts import resolver_cuenta
from api.canje import canjear, puede
from api.deletion import delete_account
from api.identity import sub_hash
from api.models import Derecho, Movimiento, SubTombstone
from api.sso import VerifiedIdentity
from api.sujetos import sujeto_natal

pytestmark = pytest.mark.django_db
URL = "/api/lectura-anonima/"
CARTA = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
    "lang": "es", "pedido": "11111111-1111-4111-8111-111111111111",
}


def _no_llamar(*a, **k):
    raise AssertionError("con el flag apagado no se toca nada de lectura_anonima")


def _sin_regalo(account):
    assert not Derecho.objects.filter(account=account, codigo_producto="lectura_breve").exists()
    assert not Movimiento.objects.filter(account=account, codigo_producto="lectura_breve").exists()
    assert puede(account, "leer_breve") is False


def test_flag_apagado_lectura_anonima_404_sin_llamar_al_llm(settings, monkeypatch):
    settings.LECTURA_BREVE_GRATIS_ENABLED = False
    # Ni el LLM, ni el cupo, ni el throttle: el 404 sale antes de todo.
    monkeypatch.setattr(la, "_build_client", _no_llamar)
    monkeypatch.setattr(la.informe_service, "escribir_breve", _no_llamar)
    monkeypatch.setattr(la, "pedir", _no_llamar)
    monkeypatch.setattr(la, "estado", _no_llamar)
    c = APIClient()
    assert c.post(URL, CARTA, format="json").status_code == 404
    assert c.get(URL, HTTP_X_LECTURA_TOKEN="x").status_code == 404


def test_flag_apagado_acuse_404_sin_tocar_la_cache(settings, monkeypatch):
    settings.LECTURA_BREVE_GRATIS_ENABLED = False
    monkeypatch.setattr(la, "acusar", _no_llamar)
    r = APIClient().delete(f"{URL}?pedido={CARTA['pedido']}", HTTP_X_LECTURA_TOKEN="x")
    assert r.status_code == 404


def test_flag_apagado_cuenta_nueva_sin_regalo(settings):
    settings.LECTURA_BREVE_GRATIS_ENABLED = False
    account, creada = resolver_cuenta(VerifiedIdentity("apple", "F0", "f0@x.com", True))
    assert creada
    _sin_regalo(account)


def test_borrar_con_flag_apagado_y_volver_con_flag_prendido_no_regala(settings):
    """Quien entró sin regalo, borró y vuelve con el flag prendido no cobra el
    regalo que nunca recibió: el tombstone anota la vida sin movimientos como
    regalo ya consumido (`deletion.free_consumidas`)."""
    settings.LECTURA_BREVE_GRATIS_ENABLED = False
    vid = VerifiedIdentity("apple", "VUELVE", "v@x.com", True)
    account, _ = resolver_cuenta(vid)
    delete_account(account)
    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "VUELVE"))
    assert tomb.free_credits_consumed == settings.INSTALL_FREE_CREDITS

    settings.LECTURA_BREVE_GRATIS_ENABLED = True
    otra, creada = resolver_cuenta(vid)
    assert creada and otra.pk != account.pk
    _sin_regalo(otra)


def test_derecho_existente_se_sigue_canjeando(settings, make_chart):
    settings.LECTURA_BREVE_GRATIS_ENABLED = True
    account, _ = resolver_cuenta(VerifiedIdentity("apple", "ANTES", "a@x.com", True))
    settings.LECTURA_BREVE_GRATIS_ENABLED = False
    assert puede(account, "leer_breve") is True
    canjear(account, "leer_breve", sujeto_natal(make_chart(account=account)))


def test_flag_prendido_regala_como_hoy(settings):
    settings.LECTURA_BREVE_GRATIS_ENABLED = True
    account, _ = resolver_cuenta(VerifiedIdentity("apple", "F1", "f1@x.com", True))
    assert Derecho.objects.filter(account=account, codigo_producto="lectura_breve").exists()
    assert Movimiento.objects.filter(account=account, codigo_producto="lectura_breve", origen="regalo").count() == 1
    assert puede(account, "leer_breve") is True
