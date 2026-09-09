"""Los dos endpoints HTTP del login por mail — RF1 y RF7.

El servicio (`api/codigos_acceso.py`) y el mail (`api/notificaciones.py`) ya
están verdes; esto es sólo la capa HTTP: pedir el código y canjearlo. Igual
que las otras dos puertas (Apple/Google), sin autenticación previa y con el
mismo trato ante un fallo de configuración: 503, nunca un 500 pelado.
"""

import pytest

from api import codigos_acceso, notificaciones
from api.models import Account, CodigoAcceso
from tests.conftest import RespuestaFalsa

pytestmark = pytest.mark.django_db

# No hay fixture `mailoutbox_stub` en este repo (el brief lo mencionaba, pero
# no existe): el fixture `resend` que stubea el POST a Resend vive en
# `tests/conftest.py`, compartido con `test_notificaciones.py`.


# --- El pedido no delata si la cuenta existe (RF1) --------------------------


def test_la_respuesta_no_delata_si_la_cuenta_existe(client, resend):
    """Si el cuerpo o el status cambiaran, cualquiera podría averiguar quién
    tiene cuenta en un sitio de astrología."""
    Account.objects.create(email="existe@gmail.com", email_verified=True)
    con = client.post("/api/auth/email/codigo",
                      {"email": "existe@gmail.com", "lang": "es"},
                      content_type="application/json")
    sin = client.post("/api/auth/email/codigo",
                      {"email": "no-existe@gmail.com", "lang": "es"},
                      content_type="application/json")
    assert con.status_code == sin.status_code == 202
    assert con.json() == sin.json()
    # Y el envío ocurrió en las dos ramas: no hay diferencia observable.
    assert len(resend) == 2


def test_el_pedido_no_necesita_estar_logueado(client, resend):
    r = client.post("/api/auth/email/codigo",
                    {"email": "juan@gmail.com", "lang": "es"},
                    content_type="application/json")
    assert r.status_code != 403


def test_el_pedido_sin_email_es_400(client):
    r = client.post("/api/auth/email/codigo", {"lang": "es"}, content_type="application/json")
    assert r.status_code == 400


# --- El canje (RF7) ----------------------------------------------------------


def test_el_canje_devuelve_la_misma_forma_que_google_mas_destino(client):
    """El brief original pedía `set(r.json()) == {"token","derechos",
    "account_id"}`, pero con esa forma RF16 es incumplible: la web necesita
    el `destino` en la respuesta porque el `next` de la URL no sobrevive el
    viaje a Mail en iOS (Ruling 15). Se afirma que CONTIENE los tres campos
    de Google, no que son los únicos."""
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com", "codigo": claro},
                    content_type="application/json")
    assert r.status_code == 200
    assert {"token", "derechos", "account_id"} <= set(r.json())


def test_el_canje_devuelve_el_destino_que_se_pidio(client):
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com", destino="/es/carta/abc")
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com", "codigo": claro},
                    content_type="application/json")
    assert r.json()["destino"] == "/es/carta/abc"


def test_el_canje_sin_destino_pedido_devuelve_vacio(client):
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com", "codigo": claro},
                    content_type="application/json")
    assert r.json()["destino"] == ""


def test_un_codigo_equivocado_devuelve_401_y_no_crea_cuenta(client):
    codigos_acceso.pedir("juan@gmail.com")
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com", "codigo": "000000"},
                    content_type="application/json")
    assert r.status_code == 401
    assert not Account.objects.filter(email="juan@gmail.com").exists()


def test_el_canje_sin_email_o_codigo_es_400(client):
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com"},
                    content_type="application/json")
    assert r.status_code == 400


# --- Ruling 11b: la identidad se arma con el mail de la FILA ----------------


def test_el_canje_usa_el_mail_normalizado_de_la_fila_no_el_del_request(client):
    """Si la vista armara la identidad con el string crudo del request en vez
    del `email` que devuelve `canjear()` (ya normalizado), un login con otra
    combinación de mayúsculas/minúsculas no encontraría la cuenta existente
    por comparación exacta y crearía una SEGUNDA cuenta en vez de entrar a la
    misma."""
    Account.objects.create(email="juan@gmail.com", email_verified=True)
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    r = client.post("/api/auth/email",
                    {"email": "JUAN@GMAIL.COM", "codigo": claro},
                    content_type="application/json")
    assert r.status_code == 200
    # No se filtra por casing exacto a propósito: si la vista usara el string
    # crudo del request, el bug crea una SEGUNDA fila con otra letra —
    # "JUAN@GMAIL.COM"— que un filtro por "juan@gmail.com" no vería.
    assert Account.objects.count() == 1
    assert Account.objects.get().email == "juan@gmail.com"


# --- Ruling 7: sin TOMBSTONE_HMAC_KEY, 503 y no un 500 pelado ---------------


def test_sin_tombstone_hmac_key_el_primer_canje_da_503(client, settings):
    settings.TOMBSTONE_HMAC_KEY = ""
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")
    r = client.post("/api/auth/email",
                    {"email": "juan@gmail.com", "codigo": claro},
                    content_type="application/json")
    assert r.status_code == 503
    assert r.json() == {"error": "login no disponible"}
    # El código ya se quemó (se comparó bien); no queda una cuenta a medio crear.
    assert not Account.objects.filter(email="juan@gmail.com").exists()


# --- Ruling 13: si el mail no sale, se devuelve el cupo y 503 ---------------


def test_sin_resend_configurado_el_pedido_devuelve_el_cupo_y_503(client):
    """La fixture autouse de `conftest.py` deja `RESEND_API_KEY` vacía: el
    envío falla solo, sin mockear nada más."""
    r = client.post("/api/auth/email/codigo",
                    {"email": "juan@gmail.com", "lang": "es"},
                    content_type="application/json")
    assert r.status_code == 503
    assert r.json() == {"error": "login no disponible"}
    fila = CodigoAcceso.objects.get(email="juan@gmail.com")
    # `envios` arranca en 1 al crear la fila; el envío fallido lo devuelve.
    assert fila.envios == 0


def test_el_cupo_devuelto_no_impide_pedir_de_nuevo_con_resend_arriba(client, settings, monkeypatch):
    """Cierra el ciclo: un primer intento sin Resend configurado no deja el
    cupo gastado para el segundo intento, ya con Resend arriba.

    No usa el fixture `resend` a propósito: éste configura la clave ANTES de
    que corra el cuerpo del test (se resuelve como cualquier fixture), y acá
    el primer pedido necesita salir sin ella."""
    sin_resend = client.post("/api/auth/email/codigo",
                             {"email": "juan@gmail.com", "lang": "es"},
                             content_type="application/json")
    assert sin_resend.status_code == 503

    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"
    enviados = []

    def post(url, **kwargs):
        enviados.append({"url": url, **kwargs})
        return RespuestaFalsa()

    monkeypatch.setattr(notificaciones.httpx, "post", post)

    con_resend = client.post("/api/auth/email/codigo",
                             {"email": "juan@gmail.com", "lang": "es"},
                             content_type="application/json")
    assert con_resend.status_code == 202
    assert len(enviados) == 1
