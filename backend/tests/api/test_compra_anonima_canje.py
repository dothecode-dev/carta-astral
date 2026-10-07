"""Volver de Stripe: el canje de una compra anónima pagada (RF10-RF13, RF17).
Superficie de AUTENTICACIÓN.

La regla que se prueba acá: el navegador que pagó entra sólo si la compra
CREÓ la cuenta, trae el nonce de ese checkout y es la primera vez. Cualquier
otra combinación es la misma respuesta genérica, y a un mail que ya tenía
cuenta se le manda un código, nunca una sesión.
"""

import logging

import pytest
from django.utils import timezone

from api import codigos_acceso, compra_anonima, mantenimiento, notificaciones
from api.identity import hash_token
from api.models import Account, CodigoAcceso, ProviderIdentity, Session
from tests.api.conftest import SESSION_ANONIMA

# El caché se vacía antes y después de cada test: el canje comparte el
# throttle `auth` (30/día) con el login por mail, y sin esto este archivo
# agota el cupo de los tests de `test_codigo_endpoints.py` que corren después.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("django_cache_cleared")]

URL_CANJE = "/api/checkout/anonimo/canjear/"
NONCE = "n0nce"


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(
        notificaciones, "enviar_codigo", lambda email, claro, lang: lista.append(email),
    )
    return lista


def _acreditada(anonima, cuenta, nueva):
    anonima.account, anonima.cuenta_nueva = cuenta, nueva
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()


def _canje(client, nonce=NONCE, checkout_id=SESSION_ANONIMA):
    return client.post(
        URL_CANJE, {"checkout_id": checkout_id, "nonce": nonce}, content_type="application/json",
    )


def _destino(anonima):
    return f"/es/carta/{anonima.chart.uuid}"


# --- RF10: la cuenta que creó la compra entra --------------------------------


def test_cuenta_nueva_y_nonce_correcto_abre_sesion(client, anonima, make_account):
    cuenta = make_account(email="n@mail.com", email_verified=False)
    _acreditada(anonima, cuenta, nueva=True)

    r = _canje(client)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "sesion"
    assert cuerpo["destino"] == _destino(anonima)
    assert cuerpo["account_id"] == cuenta.pk
    assert Session.objects.filter(account=cuenta).count() == 1
    anonima.refresh_from_db()
    assert anonima.canjeado_at is not None
    # El token sirve de verdad para hablar como esa cuenta.
    yo = client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {cuerpo['token']}")
    assert yo.status_code == 200


def test_sin_carta_el_destino_es_la_cuenta(client, anonima, make_account):
    cuenta = make_account(email="sc@mail.com")
    _acreditada(anonima, cuenta, nueva=True)
    anonima.chart = None
    anonima.sujeto = None
    anonima.save()

    assert _canje(client).json()["destino"] == "/es/cuenta"


# --- RF11: cualquier falla, sin sesión y sin decir cuál ----------------------


@pytest.mark.parametrize(
    "cambio", ["nonce_malo", "ya_canjeado", "no_anonima", "sin_nonce", "sin_nonce_guardado", "no_existe"],
)
def test_cualquier_falla_no_abre_sesion_y_no_dice_cual(client, anonima, make_account, cambio):
    cuenta = make_account(email="n2@mail.com")
    _acreditada(anonima, cuenta, nueva=True)
    nonce, checkout_id = NONCE, SESSION_ANONIMA
    if cambio == "nonce_malo":
        nonce = "otro"
    if cambio == "ya_canjeado":
        anonima.canjeado_at = timezone.now()
        anonima.save()
    if cambio == "no_anonima":
        anonima.anonimo = False
        anonima.save()
    if cambio == "sin_nonce":
        nonce = ""
    if cambio == "sin_nonce_guardado":
        anonima.nonce_hash = ""
        anonima.save()
    if cambio == "no_existe":
        checkout_id = "cs_test_otro"

    r = _canje(client, nonce=nonce, checkout_id=checkout_id)

    assert r.status_code == 404
    assert r.json() == {"error": "no encontrado"}
    assert not Session.objects.filter(account=cuenta).exists()


def test_un_segundo_canje_con_el_mismo_nonce_falla(client, anonima, make_account):
    cuenta = make_account(email="dos@mail.com")
    _acreditada(anonima, cuenta, nueva=True)

    assert _canje(client).json()["estado"] == "sesion"
    r = _canje(client)

    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}
    assert Session.objects.filter(account=cuenta).count() == 1


def test_el_cuerpo_sin_campos_es_el_mismo_404(client, anonima, make_account):
    _acreditada(anonima, make_account(email="v@mail.com"), nueva=True)
    r = client.post(URL_CANJE, {}, content_type="application/json")
    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}


# --- RF12: un mail que ya tenía cuenta recibe un código, nunca una sesión ----


def test_cuenta_existente_nunca_abre_sesion_y_manda_codigo(client, anonima, make_account, enviados):
    duenia = make_account(email="gustavo@gmail.com", email_verified=True)
    _acreditada(anonima, duenia, nueva=False)

    r = _canje(client)

    assert r.status_code == 200
    assert r.json() == {"estado": "codigo", "email": "g***@gmail.com", "destino": _destino(anonima)}
    assert not Session.objects.filter(account=duenia).exists()
    assert CodigoAcceso.objects.filter(email="gustavo@gmail.com", destino=_destino(anonima)).exists()
    assert enviados == ["gustavo@gmail.com"]
    anonima.refresh_from_db()
    assert anonima.canjeado_at is None


@pytest.mark.parametrize("via", ["identidad", "verificada"])
def test_adjudicada_por_la_adjudicacion_real_tampoco_abre_sesion(client, anonima, make_account, enviados, via):
    """Las dos ramas de `adjudicar` que encuentran una cuenta existente."""
    duenia = make_account(email="d@mail.com", email_verified=(via == "verificada"))
    if via == "identidad":
        ProviderIdentity.objects.create(provider="email", sub="d@mail.com", account=duenia)
    assert compra_anonima.adjudicar(SESSION_ANONIMA, "D@mail.com") == duenia
    anonima.refresh_from_db()
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()

    r = _canje(client)

    assert r.json()["estado"] == "codigo"
    assert "token" not in r.json()
    assert not Session.objects.filter(account=duenia).exists()
    assert enviados == ["d@mail.com"]


def test_con_nonce_malo_una_cuenta_existente_no_revela_el_mail(client, anonima, make_account, enviados):
    _acreditada(anonima, make_account(email="gustavo@gmail.com", email_verified=True), nueva=False)

    r = _canje(client, nonce="otro")

    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}
    assert enviados == []
    assert not CodigoAcceso.objects.exists()


def test_un_segundo_canje_de_cuenta_existente_vuelve_a_dar_codigo(client, anonima, make_account, enviados):
    _acreditada(anonima, make_account(email="gustavo@gmail.com", email_verified=True), nueva=False)

    assert _canje(client).json()["estado"] == "codigo"
    assert _canje(client).json()["estado"] == "codigo"
    assert enviados == ["gustavo@gmail.com", "gustavo@gmail.com"]


def test_con_el_cupo_de_codigos_gastado_no_reenvia(client, anonima, make_account, enviados, settings):
    settings.CODIGO_PEDIDOS_HORA = 1
    _acreditada(anonima, make_account(email="gustavo@gmail.com", email_verified=True), nueva=False)
    codigos_acceso.pedir("gustavo@gmail.com")

    r = _canje(client)

    assert r.json()["estado"] == "codigo"
    assert enviados == []


def test_si_el_mail_no_sale_se_loguea_enmascarado(client, anonima, make_account, monkeypatch, caplog):
    def falla(email, claro, lang):
        raise notificaciones.EnvioFallido("resend caído")

    monkeypatch.setattr(notificaciones, "enviar_codigo", falla)
    _acreditada(anonima, make_account(email="gustavo@gmail.com", email_verified=True), nueva=False)

    with caplog.at_level(logging.ERROR, logger="api.compra_anonima"):
        r = _canje(client)

    assert r.json()["estado"] == "codigo"
    errores = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert errores, "un envío fallido no puede pasar en silencio"
    texto = " ".join(rec.getMessage() for rec in errores)
    assert "g***@gmail.com" in texto
    assert "gustavo@gmail.com" not in texto


# --- RF13: todavía no acreditada ---------------------------------------------


def test_sin_acreditar_es_pendiente(client, anonima):
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    r = _canje(client)
    assert r.status_code == 200 and r.json() == {"estado": "pendiente"}


def test_sin_acreditar_y_nonce_malo_no_dice_pendiente(client, anonima):
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    r = _canje(client, nonce="otro")
    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}


def test_el_canje_comparte_el_throttle_de_las_puertas_de_entrada():
    from rest_framework.throttling import ScopedRateThrottle

    from api.compra_anonima_api import CheckoutCanjeView

    assert CheckoutCanjeView.throttle_scope == "auth"
    assert ScopedRateThrottle in CheckoutCanjeView.throttle_classes
    assert CheckoutCanjeView.authentication_classes == []


# --- RF14b: el canje sigue andando durante un deploy -------------------------


def test_con_mantenimiento_el_canje_sigue_respondiendo(client, anonima, make_account, monkeypatch):
    monkeypatch.setattr(mantenimiento, "activo", lambda: True)
    _acreditada(anonima, make_account(email="m@mail.com"), nueva=True)

    r = _canje(client)

    assert r.status_code == 200 and r.json()["estado"] == "sesion"


# --- RF17: entrar después con código verifica el mail ------------------------


def _entrar_con_codigo(client, email):
    _, claro, _ = codigos_acceso.pedir(email)
    return client.post("/api/auth/email", {"email": email, "codigo": claro}, content_type="application/json")


def test_entrar_con_codigo_despues_verifica_el_mail_de_la_cuenta_creada(client, anonima):
    cuenta = compra_anonima.adjudicar(SESSION_ANONIMA, "rf17@mail.com")
    anonima.refresh_from_db()
    assert anonima.cuenta_nueva is True and cuenta.email_verified is False

    r = _entrar_con_codigo(client, "rf17@mail.com")

    assert r.status_code == 200
    assert r.json()["account_id"] == cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is True
    assert Account.objects.filter(email="rf17@mail.com").count() == 1


def test_entrar_con_codigo_a_la_cuenta_creada_cierra_la_sesion_del_que_pago(client, anonima):
    """Quien pagó con un mail ajeno entró por el nonce; cuando la dueña real
    del mail prueba que es suya, el pagador pierde el acceso a sus datos."""
    cuenta = compra_anonima.adjudicar(SESSION_ANONIMA, "ajeno@mail.com")
    anonima.refresh_from_db()
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    token_pagador = _canje(client).json()["token"]
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token_pagador}").status_code == 200

    r = _entrar_con_codigo(client, "ajeno@mail.com")

    assert r.status_code == 200 and r.json()["account_id"] == cuenta.pk
    assert Session.objects.filter(account=cuenta).count() == 1
    assert not Session.objects.filter(token_hash=hash_token(token_pagador)).exists()
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token_pagador}").status_code == 401
    token_duenia = r.json()["token"]
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token_duenia}").status_code == 200


def test_entrar_con_codigo_a_una_cuenta_verificada_no_cierra_las_otras_sesiones(client, make_account):
    """El login normal desde un segundo dispositivo no echa al primero."""
    from api.auth import create_session

    cuenta = make_account(email="multi@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="multi@mail.com", account=cuenta)
    otro = create_session(cuenta)

    r = _entrar_con_codigo(client, "multi@mail.com")

    assert r.status_code == 200 and r.json()["account_id"] == cuenta.pk
    assert Session.objects.filter(account=cuenta).count() == 2
    assert Session.objects.filter(token_hash=hash_token(otro)).exists()
