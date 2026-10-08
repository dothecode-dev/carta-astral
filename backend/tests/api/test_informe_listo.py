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


def test_si_resend_falla_no_rompe(interpretacion_completa, resend, monkeypatch):
    from api import notificaciones

    def rompe(*a, **k):
        raise RuntimeError("resend caído")

    monkeypatch.setattr(notificaciones, "_post_resend", rompe)
    informe_service.avisar_informe_listo(interpretacion_completa)  # no lanza


def test_compra_acreditada_ya_no_promete_el_informe_disponible():
    from api.notificaciones import _TEXTOS

    for lang, (_, html) in _TEXTOS["compra_acreditada"].items():
        assert "disponible" not in html and "available" not in html and "disponível" not in html, lang
