"""Los avisos al admin (ventas a facturar, contracargos, disputas, el botón de
arrepentimiento) salen sólo por Telegram: sin él, el arranque lo dice SIEMPRE,
no sólo con el cobro en pesos prendido (code review del 19-10)."""

import pytest
from django.core.checks import run_checks


@pytest.mark.parametrize("prendido", [True, False])
@pytest.mark.parametrize("nombre", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
def test_sin_telegram_avisa_siempre(settings, nombre, prendido):
    settings.COBRO_ARS_ENABLED = prendido
    settings.TELEGRAM_BOT_TOKEN = "123:token"
    settings.TELEGRAM_CHAT_ID = "42"
    setattr(settings, nombre, "")

    errores = run_checks(tags=["avisos"])

    assert len(errores) == 1 and nombre in errores[0].msg
    assert "123:token" not in errores[0].msg + (errores[0].hint or "")


def test_con_telegram_no_avisa(settings):
    settings.TELEGRAM_BOT_TOKEN = "123:token"
    settings.TELEGRAM_CHAT_ID = "42"

    assert run_checks(tags=["avisos"]) == []
