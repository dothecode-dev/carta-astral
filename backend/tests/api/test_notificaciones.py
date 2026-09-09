"""El aviso al usuario, ahora que sale de verdad.

Hasta el 03-09-2026 `notificaciones._enviar` era un stub que logueaba: quien
pagaba un informe, cerraba la pestaña y se iba no se enteraba nunca de que
estaba listo —la web se lo decía en pantalla y nada más—, y a quien se le
devolvía el derecho por un informe que no se pudo entregar, tampoco.

Lo que estos tests fijan es sobre todo lo que NO puede pasar: un aviso que
falla no puede tumbar la transacción que lo precede. Corre después de mover
plata (acreditar una compra, devolver un derecho), así que una excepción acá
—Resend caído, la key vencida, el timeout— tiene que morir en el log.
"""

import httpx
import pytest

from api import notificaciones
from api.models import Account


@pytest.fixture
def cuenta(db):
    return Account.objects.create(email="alguien@example.com")


class RespuestaFalsa:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"id": "re_1"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None,  # type: ignore[arg-type]
            )

    def json(self):
        return self._payload


@pytest.fixture
def resend(monkeypatch, settings):
    """Resend configurado, con el POST capturado en vez de salir a la red."""
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"
    enviados = []

    def post(url, **kwargs):
        enviados.append({"url": url, **kwargs})
        return RespuestaFalsa()

    monkeypatch.setattr(notificaciones.httpx, "post", post)
    return enviados


def test_evento_desconocido_es_un_error_de_programacion(cuenta):
    # No se traga: un typo en el nombre del evento tiene que aparecer en
    # desarrollo, no convertirse en un aviso que nunca se manda.
    with pytest.raises(ValueError):
        notificaciones.notificar(cuenta, "no_existe", {}, lang="es")


def test_compra_acreditada_manda_un_mail_al_dueno_de_la_cuenta(cuenta, resend):
    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "es")

    assert len(resend) == 1
    cuerpo = resend[0]["json"]
    assert cuerpo["to"] == ["alguien@example.com"]
    assert cuerpo["from"] == "ASTRA <hola@send.astraguia.com>"
    assert resend[0]["headers"]["Authorization"] == "Bearer re_test_key"
    # El enlace a la cuenta: el mail sin a dónde volver no sirve de nada.
    assert "/es/cuenta" in cuerpo["html"]


def test_informe_no_entregado_avisa_que_el_derecho_volvio(cuenta, resend):
    notificaciones.notificar(
        cuenta, "informe_no_entregado", {"chart": "abc", "tier": "largo"}, "es",
    )

    cuerpo = resend[0]["json"]
    # Lo que la persona necesita saber es que no perdió lo que pagó.
    assert "no se te cobró" in cuerpo["html"] or "devolvimos" in cuerpo["html"]


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_cada_idioma_tiene_su_asunto(cuenta, resend, lang):
    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, lang)

    assert resend[0]["json"]["subject"]
    assert f"/{lang}/cuenta" in resend[0]["json"]["html"]


def test_un_idioma_que_no_existe_cae_en_espanol(cuenta, resend):
    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "de")

    assert "/es/cuenta" in resend[0]["json"]["html"]


# --- Lo que no puede pasar -------------------------------------------------


def test_resend_caido_no_propaga(cuenta, monkeypatch, settings, caplog):
    """El aviso corre DESPUÉS de mover plata. Si tira, revierte la devolución
    del derecho o deja el webhook en 5xx y Stripe reintenta una compra que ya
    se acreditó."""
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"

    def post(url, **kwargs):
        raise httpx.ConnectTimeout("sin red")

    monkeypatch.setattr(notificaciones.httpx, "post", post)

    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "es")

    # Muere en el log, pero deja rastro: un aviso que no salió y del que nadie
    # se enteró es exactamente el agujero que esto viene a tapar.
    assert "fallo el aviso" in caplog.text


def test_un_400_de_resend_tampoco_propaga(cuenta, monkeypatch, settings, caplog):
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"
    monkeypatch.setattr(
        notificaciones.httpx, "post", lambda url, **kw: RespuestaFalsa(422, {"message": "no"}),
    )

    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "es")

    assert "fallo el aviso" in caplog.text


def test_sin_key_configurada_no_intenta_mandar(cuenta, monkeypatch, settings, caplog):
    """En desarrollo y en los tests de todo lo demás no hay key: el aviso queda
    en el log, como antes, sin ensuciar la salida con un error."""
    settings.RESEND_API_KEY = ""
    llamado = []
    monkeypatch.setattr(notificaciones.httpx, "post", lambda *a, **k: llamado.append(1))

    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "es")

    assert llamado == []
    assert "fallo el aviso" not in caplog.text


def test_una_cuenta_sin_mail_no_intenta_mandar(db, resend):
    """Las cuentas de Apple con "ocultar mi correo" pueden no tener mail, y las
    de dev tampoco."""
    sin_mail = Account.objects.create(email="")

    notificaciones.notificar(sin_mail, "compra_acreditada", {"producto": "informe_natal"}, "es")

    assert resend == []


# --- El código de acceso ----------------------------------------------------
#
# Todavía no hay `Account` cuando se manda el código —se crea recién al
# canjear—, así que estas dos funciones son la variante de `textos_codigo` /
# `enviar_codigo` que reciben la dirección directo en vez de una cuenta.


def test_el_codigo_va_tambien_en_el_asunto():
    """Para que se lea desde la notificación del teléfono sin abrir el mail:
    11 de 14 visitantes están en un iPhone."""
    asunto, _ = notificaciones.textos_codigo("es", "123456")
    assert "123456" in asunto


def test_existe_en_los_tres_idiomas():
    for lang in ("es", "en", "pt"):
        asunto, html = notificaciones.textos_codigo(lang, "123456")
        assert asunto and "123456" in html


def test_no_se_loguea_ni_el_codigo_ni_la_direccion(caplog):
    # Sin key configurada esto ahora levanta `EnvioFallido` (Ruling 13): el
    # mail ES el mecanismo de acceso, no un aviso accesorio. Lo que este test
    # sigue fijando es que ni el código ni la dirección aparecen en el log,
    # levante o no.
    with pytest.raises(notificaciones.EnvioFallido):
        notificaciones.enviar_codigo("juan@gmail.com", "123456", "es")
    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "123456" not in registro
    assert "juan@gmail.com" not in registro


# --- Ruling 13: enviar_codigo() señala el fallo, no lo traga ---------------
#
# A diferencia de `notificar` —eventos accesorios de algo que ya pasó y que
# la persona puede ver igual entrando a la cuenta—, acá el mail ES el
# mecanismo de acceso. Tragarse la falla deja a alguien esperando un código
# que nunca va a llegar, con el cupo de la hora ya gastado y ninguna señal en
# ningún lado. Por eso `enviar_codigo` propaga `EnvioFallido` y es tarea del
# endpoint (Tarea 7) decidir qué hacer con eso.


def test_enviar_codigo_sin_key_configurada_levanta_envio_fallido(caplog):
    with pytest.raises(notificaciones.EnvioFallido):
        notificaciones.enviar_codigo("juan@gmail.com", "123456", "es")


def test_enviar_codigo_resend_caido_levanta_envio_fallido(monkeypatch, settings, caplog):
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"

    def post(url, **kwargs):
        raise httpx.ConnectTimeout("sin red")

    monkeypatch.setattr(notificaciones.httpx, "post", post)

    with pytest.raises(notificaciones.EnvioFallido):
        notificaciones.enviar_codigo("juan@gmail.com", "123456", "es")

    registro = "\n".join(r.getMessage() for r in caplog.records)
    assert "123456" not in registro
    assert "juan@gmail.com" not in registro


def test_enviar_codigo_un_400_de_resend_tambien_levanta_envio_fallido(
    monkeypatch, settings, caplog,
):
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"
    monkeypatch.setattr(
        notificaciones.httpx, "post", lambda url, **kw: RespuestaFalsa(422, {"message": "no"}),
    )

    with pytest.raises(notificaciones.EnvioFallido):
        notificaciones.enviar_codigo("juan@gmail.com", "123456", "es")


def test_enviar_codigo_camino_feliz_no_levanta_nada(resend):
    notificaciones.enviar_codigo("juan@gmail.com", "123456", "es")

    assert len(resend) == 1
    cuerpo = resend[0]["json"]
    assert cuerpo["to"] == ["juan@gmail.com"]
    assert "123456" in cuerpo["html"]


def test_notificar_de_los_otros_eventos_sigue_tragandose_la_falla(cuenta, monkeypatch, settings, caplog):
    """Ruling 13 es sólo para `enviar_codigo`: los otros eventos son avisos
    accesorios y siguen sin propagar."""
    settings.RESEND_API_KEY = "re_test_key"
    settings.MAIL_FROM = "ASTRA <hola@send.astraguia.com>"

    def post(url, **kwargs):
        raise httpx.ConnectTimeout("sin red")

    monkeypatch.setattr(notificaciones.httpx, "post", post)

    # No debe levantar nada: notificar/_enviar mantienen su comportamiento.
    notificaciones.notificar(cuenta, "compra_acreditada", {"producto": "informe_natal"}, "es")

    assert "fallo el aviso" in caplog.text
