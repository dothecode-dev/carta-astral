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
from api.sujetos import sujeto_natal
from tests.api.conftest import SESSION_ANONIMA

# El caché (donde viven los baldes de throttle) se vacía antes y después de
# cada test: este archivo también entra por código (`auth`, 30/día) y prueba
# baldes del canje; sin vaciarlo, el resultado dependería del orden.
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
    return f"/es/carta/{anonima.sujeto.natal_de.uuid}"


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
    duenia = make_account(email="gustavo@example.com", email_verified=True)
    _acreditada(anonima, duenia, nueva=False)

    r = _canje(client)

    assert r.status_code == 200
    assert r.json() == {"estado": "codigo", "email": "g***@example.com", "destino": _destino(anonima)}
    assert not Session.objects.filter(account=duenia).exists()
    assert CodigoAcceso.objects.filter(email="gustavo@example.com", destino=_destino(anonima)).exists()
    assert enviados == ["gustavo@example.com"]
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
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)

    r = _canje(client, nonce="otro")

    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}
    assert enviados == []
    assert not CodigoAcceso.objects.exists()


def test_recargar_la_pagina_no_manda_otro_mail(client, anonima, make_account, enviados):
    """Un segundo canje de una cuenta existente vuelve a dar `codigo` (no es un
    secreto que se gaste), pero si ya hay un código vigente reciente para ese
    mail y ese destino no se pide ni se manda otro: recargar /compra no es
    otro mail."""
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)

    assert _canje(client).json()["estado"] == "codigo"
    assert _canje(client).json() == {
        "estado": "codigo", "email": "g***@example.com", "destino": _destino(anonima),
    }
    assert enviados == ["gustavo@example.com"]
    assert CodigoAcceso.objects.filter(email="gustavo@example.com").count() == 1


def test_pasados_diez_minutos_si_manda_otro_codigo(client, anonima, make_account, enviados):
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)
    _canje(client)
    CodigoAcceso.objects.update(creado_en=timezone.now() - timezone.timedelta(minutes=11))

    _canje(client)

    assert enviados == ["gustavo@example.com", "gustavo@example.com"]


def test_un_codigo_usado_no_frena_el_siguiente(client, anonima, make_account, enviados):
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)
    _canje(client)
    CodigoAcceso.objects.update(usado_en=timezone.now())

    _canje(client)

    assert len(enviados) == 2


def test_con_el_cupo_de_codigos_gastado_no_reenvia(client, anonima, make_account, enviados, settings):
    settings.CODIGO_PEDIDOS_HORA = 1
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)
    codigos_acceso.pedir("gustavo@example.com")

    r = _canje(client)

    assert r.json()["estado"] == "codigo"
    assert enviados == []


def test_si_el_mail_no_sale_se_loguea_enmascarado(client, anonima, make_account, monkeypatch, caplog):
    def falla(email, claro, lang):
        raise notificaciones.EnvioFallido("resend caído")

    monkeypatch.setattr(notificaciones, "enviar_codigo", falla)
    _acreditada(anonima, make_account(email="gustavo@example.com", email_verified=True), nueva=False)

    with caplog.at_level(logging.ERROR, logger="api.compra_anonima"):
        r = _canje(client)

    assert r.json()["estado"] == "codigo"
    errores = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert errores, "un envío fallido no puede pasar en silencio"
    texto = " ".join(rec.getMessage() for rec in errores)
    assert "g***@example.com" in texto
    assert "gustavo@example.com" not in texto


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


def test_el_canje_no_gasta_el_cupo_del_login(client, anonima, resend):
    """La web sondea el canje mientras está `pendiente` (RF13): si compartiera
    el balde `auth` (30/día por IP), un webhook lento dejaría a quien pagó sin
    poder entrar por código ni por Google el resto del día."""
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    for _ in range(40):
        assert _canje(client).json() == {"estado": "pendiente"}

    r = client.post("/api/auth/email/codigo", {"email": "p@mail.com", "lang": "es"},
                    content_type="application/json")

    assert r.status_code == 202


def test_el_canje_tiene_su_propio_techo(client, anonima, monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"canje_compra": "2/hour", "auth": "30/day"},
    )
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()

    estados = [_canje(client).status_code for _ in range(3)]

    assert estados == [200, 200, 429]


# --- Canje tardío: la cuenta ya no es «nueva» -------------------------------


def test_si_la_duenia_del_mail_entro_antes_el_nonce_ya_no_abre_sesion(client, anonima, enviados):
    """El atacante paga con el mail de la víctima (sin cuenta) y no canjea; la
    víctima entra con código (RF17: la cuenta se verifica); después el
    atacante canjea con su nonce. No puede recibir un token de esa cuenta."""
    cuenta = compra_anonima.adjudicar(SESSION_ANONIMA, "victima@mail.com")
    anonima.refresh_from_db()
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    assert _entrar_con_codigo(client, "victima@mail.com").status_code == 200
    sesiones_antes = Session.objects.filter(account=cuenta).count()

    r = _canje(client)

    assert r.status_code == 200
    assert r.json() == {"estado": "codigo", "email": "v***@mail.com", "destino": _destino(anonima)}
    assert Session.objects.filter(account=cuenta).count() == sesiones_antes
    anonima.refresh_from_db()
    assert anonima.canjeado_at is None


@pytest.mark.parametrize("nueva", [True, False])
def test_pasadas_24_horas_el_nonce_ya_no_sirve_para_nada(client, anonima, make_account, enviados, nueva):
    """Nadie legítimo conserva el nonce más de 24 h (RF2): pasado eso, ni
    sesión ni código. Si no, quien guardó el nonce podría seguir disparando
    mails a la dueña del mail para siempre."""
    cuenta = make_account(email="tarde@mail.com", email_verified=not nueva)
    _acreditada(anonima, cuenta, nueva=nueva)
    anonima.acreditado_at = timezone.now() - timezone.timedelta(hours=25)
    anonima.save()

    r = _canje(client)

    assert r.status_code == 404 and r.json() == {"error": "no encontrado"}
    assert not Session.objects.filter(account=cuenta).exists()
    assert enviados == []
    assert not CodigoAcceso.objects.exists()


def test_la_verificacion_entre_la_lectura_y_el_lock_de_la_cuenta_gana(client, anonima, monkeypatch, enviados):
    """Carrera canje ↔ login por código. El lock del canje es sobre la fila
    del checkout, no sobre la cuenta: la cuenta que trae el `select_related`
    puede quedar vieja si un login por código la verifica (y borra sus
    sesiones) justo después. No es determinista como test de hilos, así que
    se simula: `hash_token` corre después de leer la fila y antes de decidir,
    y ahí se verifica la cuenta en la base. El canje tiene que releerla con
    lock y no abrir sesión."""
    cuenta = compra_anonima.adjudicar(SESSION_ANONIMA, "carrera@mail.com")
    anonima.refresh_from_db()
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()

    def hash_y_login_en_paralelo(valor):
        Account.objects.filter(pk=cuenta.pk).update(email_verified=True)
        return hash_token(valor)

    monkeypatch.setattr(compra_anonima, "hash_token", hash_y_login_en_paralelo)

    r = _canje(client)

    assert r.json()["estado"] == "codigo"
    assert "token" not in r.json()
    assert not Session.objects.filter(account=cuenta).exists()


def test_poco_antes_de_las_24_horas_el_nonce_si_abre_sesion(client, anonima, make_account):
    cuenta = make_account(email="justo@mail.com", email_verified=False)
    _acreditada(anonima, cuenta, nueva=True)
    anonima.acreditado_at = timezone.now() - timezone.timedelta(hours=23)
    anonima.save()

    assert _canje(client).json()["estado"] == "sesion"


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


#: La segunda compra sin cuenta con el mismo mail (la de la dueña real).
SESSION_VICTIMA = "cs_test_victima"


def _segunda_compra(make_chart, email):
    """Otra compra anónima con `email`, adjudicada: la de la dueña del mail."""
    from api.models import PasarelaCheckout

    fila = PasarelaCheckout.objects.create(
        checkout_id=SESSION_VICTIMA, account=None, codigo_producto="informe_natal",
        sujeto=sujeto_natal(make_chart(account=None)), anonimo=True, nonce_hash=hash_token("otro-nonce"),
        precio_centavos=2900,
    )
    cuenta = compra_anonima.adjudicar(SESSION_VICTIMA, email)
    fila.refresh_from_db()
    return fila, cuenta


def _primera_compra_del_atacante(anonima, email):
    cuenta = compra_anonima.adjudicar(SESSION_ANONIMA, email)
    anonima.refresh_from_db()
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()
    return cuenta


def test_una_segunda_compra_sobre_la_cuenta_sin_verificar_cierra_las_sesiones(client, anonima, make_chart):
    """Review 07-10, punto 1 (a). El atacante paga sin cuenta con el mail de
    la víctima y entra por el nonce: cuenta A sin verificar con la identidad
    email. Cuando la víctima compra sin cuenta con su mail, la compra va a A
    (es donde ella va a entrar con el código), pero el atacante no puede
    seguir mirando: sus sesiones en A se cierran."""
    cuenta = _primera_compra_del_atacante(anonima, "victima2@mail.com")
    token_atacante = _canje(client).json()["token"]
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token_atacante}").status_code == 200

    fila, adjudicada = _segunda_compra(make_chart, "victima2@mail.com")

    assert adjudicada == cuenta and fila.cuenta_nueva is False
    assert not Session.objects.filter(account=cuenta).exists()
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token_atacante}").status_code == 401
    cuenta.refresh_from_db()
    assert cuenta.email_verified is False  # nadie probó el mail en la adjudicación


def test_un_nonce_sin_canjear_de_la_primera_compra_ya_no_abre_sesion(client, anonima, make_chart, enviados):
    """Review 07-10, punto 1 (b). Variante: el atacante guarda el nonce sin
    canjear y lo canjea DESPUÉS de la compra de la víctima (dentro de las 24
    h). La cuenta sigue sin verificar, así que `_cuenta_nueva_sin_verificar`
    sola le abriría sesión: la adjudicación tiene que haber gastado ese nonce."""
    cuenta = _primera_compra_del_atacante(anonima, "victima3@mail.com")
    _segunda_compra(make_chart, "victima3@mail.com")

    r = _canje(client)

    assert r.status_code in (200, 404)
    assert "token" not in r.json()
    if r.status_code == 200:
        assert r.json()["estado"] == "codigo"
    assert not Session.objects.filter(account=cuenta).exists()


def test_la_duenia_entra_con_codigo_y_ve_su_carta(client, anonima, make_chart, enviados):
    """Review 07-10, punto 1 (c): la compra de la dueña quedó en la cuenta A;
    entrando con el código cae ahí, la cuenta se verifica y ve su carta."""
    cuenta = _primera_compra_del_atacante(anonima, "victima4@mail.com")
    _canje(client)
    fila, _ = _segunda_compra(make_chart, "victima4@mail.com")

    r = _entrar_con_codigo(client, "victima4@mail.com")

    assert r.status_code == 200 and r.json()["account_id"] == cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is True
    token = r.json()["token"]
    carta = client.get(f"/api/charts/{fila.sujeto.natal_de.uuid}/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert carta.status_code == 200


def test_una_compra_sobre_una_cuenta_verificada_no_cierra_sus_sesiones(client, anonima, make_account):
    """Review 07-10, punto 1 (d): con el mail verificado el comportamiento no
    cambia; la dueña probó su mail y sus sesiones son suyas."""
    from api.auth import create_session

    cuenta = make_account(email="verif@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="verif@mail.com", account=cuenta)
    token = create_session(cuenta)

    assert compra_anonima.adjudicar(SESSION_ANONIMA, "verif@mail.com") == cuenta

    assert Session.objects.filter(token_hash=hash_token(token)).exists()
    assert client.get("/api/account/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200


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
