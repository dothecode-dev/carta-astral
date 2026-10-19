"""Botón de arrepentimiento (Res. SCI 424/2020). Mini-spec en
docs/2026-10-19-mini-spec-boton-arrepentimiento.md.

El formulario es público y NO mueve plata (decisión de Gustavo, 19-10): guarda
la solicitud, devuelve un código, lo manda por mail y avisa al admin, que
reembolsa a mano. La respuesta es la misma haya o no compras con ese mail.
"""

import datetime as dt
import re

import pytest
from django.utils import timezone

from api import arrepentimiento, notificaciones
from api.models import PasarelaCheckout, SolicitudArrepentimiento

URL = "/api/arrepentimiento/"
CODIGO = re.compile(r"^ARR-[A-Z2-9]{8}$")


@pytest.fixture(autouse=True)
def _cache_limpia(django_cache_cleared):
    """El techo por IP vive en la caché: sin limpiarla, los tests se lo gastan entre sí."""


@pytest.fixture
def avisos(monkeypatch):
    enviados = []
    monkeypatch.setattr(arrepentimiento, "avisar_admin", enviados.append)
    return enviados


@pytest.fixture
def mails(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        notificaciones, "enviar_arrepentimiento",
        lambda email, codigo, lang: enviados.append((email, codigo, lang)),
    )
    return enviados


def _pedir(client, **datos):
    return client.post(URL, data={"email": "ana@example.com", "locale": "es", **datos}, content_type="application/json")


def _compra(cuenta, checkout_id, dias=1, moneda="ars"):
    return PasarelaCheckout.objects.create(
        checkout_id=checkout_id, account=cuenta, codigo_producto="informe_natal", moneda=moneda,
        precio_centavos=2_500_000, pasarela=PasarelaCheckout.MERCADOPAGO, locale="es",
        acreditado_at=timezone.now() - dt.timedelta(days=dias),
    )


@pytest.mark.django_db
def test_registra_responde_el_codigo_y_lo_manda_por_mail(client, avisos, mails):
    r = _pedir(client, numero_compra="a1b2c3d4e5")

    assert r.status_code == 201
    codigo = r.json()["codigo"]
    assert CODIGO.match(codigo)
    solicitud = SolicitudArrepentimiento.objects.get()
    assert (solicitud.codigo, solicitud.email, solicitud.numero_compra) == (codigo, "ana@example.com", "a1b2c3d4e5")
    assert solicitud.estado == SolicitudArrepentimiento.PENDIENTE
    assert mails == [("ana@example.com", codigo, "es")]
    assert len(avisos) == 1 and codigo in avisos[0] and "a***@example.com" in avisos[0]
    assert "ana@example.com" not in avisos[0]


@pytest.mark.django_db
def test_el_aviso_lista_las_compras_recientes_de_ese_mail(client, avisos, mails, make_account):
    cuenta = make_account(email="ana@example.com")
    _compra(cuenta, "mp_" + "1" * 32, dias=2)
    _compra(cuenta, "mp_" + "2" * 32, dias=45)  # fuera de los 30 días
    _compra(make_account(email="otro@example.com"), "mp_" + "3" * 32)

    _pedir(client, email="ANA@example.com ")

    assert "mp_" + "1" * 32 in avisos[0]
    assert "mp_" + "2" * 32 not in avisos[0] and "mp_" + "3" * 32 not in avisos[0]


@pytest.mark.django_db
def test_compra_sin_cuenta_por_mail_comprador_tambien_aparece(client, avisos, mails):
    PasarelaCheckout.objects.create(
        checkout_id="mp_" + "4" * 32, codigo_producto="informe_natal", moneda="ars", precio_centavos=2_500_000,
        pasarela=PasarelaCheckout.MERCADOPAGO, locale="es", mail_comprador="ana@example.com", anonimo=True,
        acreditado_at=timezone.now(),
    )

    _pedir(client)

    assert "mp_" + "4" * 32 in avisos[0]


@pytest.mark.django_db
def test_la_respuesta_es_la_misma_con_o_sin_compras(client, avisos, mails, make_account):
    sin = _pedir(client, email="nadie@example.com")
    _compra(make_account(email="ana@example.com"), "mp_" + "5" * 32)
    con = _pedir(client)

    assert sin.status_code == con.status_code == 201
    assert sin.json().keys() == con.json().keys() == {"codigo"}


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["", "sin-arroba", None])
def test_mail_invalido_400_y_no_guarda(client, avisos, mails, email):
    r = client.post(URL, data={"email": email}, content_type="application/json")

    assert r.status_code == 400
    assert r.json()["motivo"] == "email_invalido"
    assert not SolicitudArrepentimiento.objects.exists()
    assert mails == [] and avisos == []


@pytest.mark.django_db
def test_si_el_mail_no_sale_la_solicitud_queda_y_el_admin_se_entera(client, avisos, monkeypatch):
    def falla(email, codigo, lang):
        raise notificaciones.EnvioFallido("caído")

    monkeypatch.setattr(notificaciones, "enviar_arrepentimiento", falla)

    r = _pedir(client)

    assert r.status_code == 201
    assert SolicitudArrepentimiento.objects.filter(codigo=r.json()["codigo"]).exists()
    assert len(avisos) == 1 and "mail" in avisos[0].lower() and "no salió" in avisos[0]


@pytest.mark.django_db
def test_numero_de_compra_raro_se_limpia(client, avisos, mails):
    _pedir(client, numero_compra="<script>" + "x" * 100)

    numero = SolicitudArrepentimiento.objects.get().numero_compra
    assert len(numero) <= 40 and "<" not in numero


@pytest.mark.django_db
def test_idioma_desconocido_cae_a_espanol(client, avisos, mails):
    _pedir(client, locale="fr")

    assert mails[0][2] == "es"


def test_tiene_techo_por_ip(settings):
    from api.arrepentimiento_api import ArrepentimientoView

    assert ArrepentimientoView.throttle_scope == "arrepentimiento"
    assert "arrepentimiento" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert ArrepentimientoView.authentication_classes == []


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_el_mail_lleva_el_codigo_en_su_idioma(lang):
    asunto, html, texto = notificaciones.armar_arrepentimiento(lang, "ARR-ABCD2345")

    assert "ARR-ABCD2345" in asunto and "ARR-ABCD2345" in html and "ARR-ABCD2345" in texto


def test_el_admin_no_borra_ni_inventa_solicitudes(rf):
    """Son la constancia de la revocación: como los reembolsos, no se borran
    ni se cargan a mano; sólo se marcan resueltas."""
    from django.contrib import admin

    modelo_admin = admin.site._registry[SolicitudArrepentimiento]
    request = rf.get("/")
    assert modelo_admin.has_delete_permission(request) is False
    assert modelo_admin.has_add_permission(request) is False
