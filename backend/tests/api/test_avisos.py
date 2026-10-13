# backend/tests/api/test_avisos.py
"""`avisar_admin`: un POST a Telegram que nunca rompe lo que avisa."""

import httpx
import pytest

from api import avisos


@pytest.fixture
def telegram(monkeypatch, settings):
    settings.TELEGRAM_BOT_TOKEN = "123:abc"
    settings.TELEGRAM_CHAT_ID = "-100777"
    llamadas = []

    def post(url, json=None, timeout=None):
        llamadas.append({"url": url, "json": json, "timeout": timeout})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(avisos.httpx, "post", post)
    return llamadas


def test_manda_el_texto_al_chat_configurado(telegram):
    avisos.avisar_admin("disputa du_1: R$ 149,00")

    assert telegram[0]["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert telegram[0]["json"] == {"chat_id": "-100777", "text": "disputa du_1: R$ 149,00"}
    assert telegram[0]["timeout"] is not None


def test_sin_token_no_llama_a_nadie(telegram, settings):
    settings.TELEGRAM_BOT_TOKEN = ""

    avisos.avisar_admin("algo")

    assert telegram == []


def test_un_fallo_de_red_no_levanta_y_no_loguea_el_token(monkeypatch, settings, caplog):
    settings.TELEGRAM_BOT_TOKEN = "123:secreto"
    settings.TELEGRAM_CHAT_ID = "1"

    def post(url, json=None, timeout=None):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(avisos.httpx, "post", post)

    avisos.avisar_admin("algo")  # no levanta

    assert "secreto" not in caplog.text
    assert "telegram" in caplog.text.lower()


def test_una_excepcion_que_no_es_httperror_tampoco_levanta(monkeypatch, settings, caplog):
    """`InvalidURL` (un token con caracteres raros) no hereda de `HTTPError`:
    si escapara, el webhook respondería 5xx y Stripe reintentaría en loop."""
    settings.TELEGRAM_BOT_TOKEN = "123:secreto"
    settings.TELEGRAM_CHAT_ID = "1"

    def post(url, json=None, timeout=None):
        raise httpx.InvalidURL(f"x {url}")

    monkeypatch.setattr(avisos.httpx, "post", post)

    with caplog.at_level("WARNING", logger="api.avisos"):
        avisos.avisar_admin("algo")  # no levanta

    assert "InvalidURL" in caplog.text
    assert "secreto" not in caplog.text


def test_un_4xx_tampoco_levanta(monkeypatch, settings, caplog):
    settings.TELEGRAM_BOT_TOKEN = "123:abc"
    settings.TELEGRAM_CHAT_ID = "1"
    monkeypatch.setattr(
        avisos.httpx, "post",
        lambda url, json=None, timeout=None: httpx.Response(
            400, request=httpx.Request("POST", url), json={"description": "chat not found"},
        ),
    )

    avisos.avisar_admin("algo")

    assert "400" in caplog.text


def test_el_texto_se_recorta_al_tope_de_telegram(telegram):
    avisos.avisar_admin("x" * 5000)

    assert len(telegram[0]["json"]["text"]) == 4000


def test_el_token_se_lee_sin_espacios_ni_saltos(monkeypatch):
    """Pegado en Coolify con un salto de línea al final: tiene que servir igual."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", " 123:abc\n")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "7\n")
    import importlib

    from config import settings as s

    importlib.reload(s)
    assert s.TELEGRAM_BOT_TOKEN == "123:abc"
    assert s.TELEGRAM_CHAT_ID == "7"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    importlib.reload(s)
