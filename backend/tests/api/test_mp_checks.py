import pytest
from django.core.checks import run_checks


def _configurar(settings):
    settings.COBRO_ARS_ENABLED = True
    settings.MP_ACCESS_TOKEN = "APP_USR-secreto-token"
    settings.MP_WEBHOOK_SECRET = "secreto-webhook"
    settings.MP_NOTIFICACION_URL = "https://api.example.com/webhooks/mp/"
    settings.MP_RETORNO_URL = "https://example.com/{locale}/compra?checkout_id={checkout_id}"


def test_flag_apagado_sin_avisos(settings, monkeypatch):
    from api import avisos

    settings.COBRO_ARS_ENABLED = False
    settings.MP_ACCESS_TOKEN = ""
    settings.MP_WEBHOOK_SECRET = ""
    settings.MP_NOTIFICACION_URL = ""
    settings.MP_RETORNO_URL = ""
    monkeypatch.setenv("AVISAR_CHECKS", "1")
    avisados = []
    monkeypatch.setattr(avisos, "avisar_admin", avisados.append)

    assert run_checks(tags=["mercadopago"]) == []
    assert avisados == []


def test_falta_token_avisa(settings, monkeypatch):
    from api import avisos

    _configurar(settings)
    settings.MP_ACCESS_TOKEN = ""
    monkeypatch.setenv("AVISAR_CHECKS", "1")
    avisados = []
    monkeypatch.setattr(avisos, "avisar_admin", avisados.append)

    errores = run_checks(tags=["mercadopago"])

    assert len(errores) == 1
    assert "MP_ACCESS_TOKEN" in errores[0].msg
    assert avisados and "MP_ACCESS_TOKEN" in avisados[0]


def test_sin_avisar_checks_vuelve_el_warning_pero_no_se_avisa(settings, monkeypatch):
    from api import avisos

    _configurar(settings)
    settings.MP_WEBHOOK_SECRET = ""
    monkeypatch.delenv("AVISAR_CHECKS", raising=False)
    avisados = []
    monkeypatch.setattr(avisos, "avisar_admin", avisados.append)

    errores = run_checks(tags=["mercadopago"])

    assert len(errores) == 1 and "MP_WEBHOOK_SECRET" in errores[0].msg
    assert avisados == []


def test_url_http_avisa(settings):
    _configurar(settings)
    settings.MP_NOTIFICACION_URL = "http://api.example.com/webhooks/mp/"

    errores = run_checks(tags=["mercadopago"])

    assert len(errores) == 1
    assert "MP_NOTIFICACION_URL" in errores[0].msg
    assert "https" in errores[0].msg


def test_el_warning_no_filtra_el_valor_de_los_secretos(settings):
    _configurar(settings)
    settings.MP_RETORNO_URL = ""
    settings.MP_NOTIFICACION_URL = "http://x"

    for e in run_checks(tags=["mercadopago"]):
        assert "secreto" not in e.msg + (e.hint or "")


def test_todo_configurado_sin_avisos(settings):
    _configurar(settings)

    assert run_checks(tags=["mercadopago"]) == []



@pytest.mark.parametrize("url,falta", [
    ("https://example.com/{locale}/compra", "{checkout_id}"),
    ("https://example.com/es/compra?checkout_id={checkout_id}", "{locale}"),
    ("https://example.com/cuenta", "{checkout_id}"),
])
def test_url_de_retorno_sin_marcadores_avisa(settings, url, falta):
    """Code review I: sin `{checkout_id}` la web no sabe qué compra esperar al
    volver de MP; sin `{locale}` vuelve en otro idioma."""
    _configurar(settings)
    settings.MP_RETORNO_URL = url

    errores = run_checks(tags=["mercadopago"])

    assert errores and all("MP_RETORNO_URL" in e.msg for e in errores)
    assert any(falta in e.msg for e in errores)
