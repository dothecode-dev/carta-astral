import pytest

from api import informe_service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cuenta_con_mail(interpretacion_completa):
    # La cuenta de la fixture no tiene mail y `_enviar` no manda sin destinatario.
    cuenta = interpretacion_completa.account
    cuenta.email = "lectora@example.com"
    cuenta.save()


def test_informe_listo_se_avisa_una_vez(interpretacion_completa, resend):
    informe_service.avisar_informe_listo(interpretacion_completa)
    informe_service.avisar_informe_listo(interpretacion_completa)
    assert len(resend) == 1
    assert "listo" in str(resend[0]).lower()


def test_la_breve_no_se_avisa(interpretacion_completa, resend):
    interpretacion_completa.tier = "corto"
    interpretacion_completa.save()
    informe_service.avisar_informe_listo(interpretacion_completa)
    assert resend == []


def test_si_resend_falla_no_rompe(interpretacion_completa, resend, monkeypatch, caplog):
    from api import notificaciones

    def rompe(*a, **k):
        raise RuntimeError("resend caído")

    monkeypatch.setattr(notificaciones, "_post_resend", rompe)
    texto_antes = interpretacion_completa.text
    with caplog.at_level("ERROR", logger="api.notificaciones"):
        informe_service.avisar_informe_listo(interpretacion_completa)  # no lanza

    # `notificar` loguea el fallo con traceback.
    assert any(
        r.name == "api.notificaciones" and r.levelname == "ERROR" and r.exc_info
        for r in caplog.records
    )
    # Entrega at-most-once: queda marcada aunque Resend haya fallado.
    interpretacion_completa.refresh_from_db()
    assert interpretacion_completa.avisada_at is not None
    assert interpretacion_completa.completa is True
    assert interpretacion_completa.text == texto_antes


def test_compra_acreditada_ya_no_promete_el_informe_disponible():
    from api.notificaciones import _TEXTOS

    for lang, (_, html) in _TEXTOS["compra_acreditada"].items():
        assert "disponible" not in html and "available" not in html and "disponível" not in html, lang


def test_compra_acreditada_es_generica_e_informe_en_curso_promete_el_mail():
    """Spec §11, RF24 v3: `compra_acreditada` sale para cualquier producto (un
    pack, una compra que saldó deuda) y no puede prometer un informe que no
    se está escribiendo; eso lo dice `informe_en_curso`."""
    from api.notificaciones import EVENTOS, _TEXTOS

    assert "informe_en_curso" in EVENTOS
    for lang in ("es", "en", "pt"):
        _, generico = _TEXTOS["compra_acreditada"][lang]
        _, en_curso = _TEXTOS["informe_en_curso"][lang]
        assert not any(p in generico for p in ("escribiendo", "writing", "escrevendo")), lang
        assert any(p in en_curso for p in ("escribiendo", "writing", "escrevendo")), lang


def test_informe_listo_lleva_a_la_pagina_del_informe(interpretacion_completa, resend, settings):
    """Spec §11, RF24 v3: el informe vive en la página de la carta
    (`web/app/[locale]/carta/[id]`, `id` = uuid), no en la cuenta."""
    settings.WEB_BASE_URL = "https://astraguia.com/"
    interpretacion_completa.lang = "pt"
    interpretacion_completa.save()
    informe_service.avisar_informe_listo(interpretacion_completa)
    html = resend[0]["json"]["html"]
    uuid = interpretacion_completa.sujeto.natal_de.uuid
    assert f'href="https://astraguia.com/pt/carta/{uuid}"' in html


def test_los_otros_avisos_siguen_llevando_a_la_cuenta(interpretacion_completa, resend, settings):
    from api import notificaciones

    settings.WEB_BASE_URL = "https://astraguia.com"
    notificaciones.notificar(interpretacion_completa.account, "compra_acreditada", {"producto": "x"}, "es")
    assert 'href="https://astraguia.com/es/cuenta"' in resend[0]["json"]["html"]


@pytest.mark.parametrize("ruta", ["https://otro.example/x", "//otro.example/x", "carta/x", 5])
def test_una_ruta_que_no_es_del_sitio_no_se_usa(interpretacion_completa, resend, settings, ruta):
    from api import notificaciones

    settings.WEB_BASE_URL = "https://astraguia.com"
    notificaciones.notificar(interpretacion_completa.account, "informe_listo", {"ruta": ruta}, "es")
    assert 'href="https://astraguia.com/es/cuenta"' in resend[0]["json"]["html"]
