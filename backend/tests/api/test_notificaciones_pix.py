"""El mail de una compra con Pix avisa que el cargo aparece como «Ebanx»."""

from api import notificaciones


def test_con_pix_el_mail_dice_que_el_cargo_aparece_como_ebanx():
    asunto, html, texto = notificaciones._armar(
        "informe_en_curso", {"producto": "informe_natal", "medio": "pix"}, "pt", "https://astraguia.com/pt/cuenta",
    )
    assert "Ebanx" in texto and "Ebanx" in html


def test_con_tarjeta_no_lo_dice():
    _, _, texto = notificaciones._armar(
        "informe_en_curso", {"producto": "informe_natal", "medio": "card"}, "pt", "https://astraguia.com/pt/cuenta",
    )
    assert "Ebanx" not in texto


def test_en_los_tres_idiomas():
    for lang in ("es", "en", "pt"):
        _, _, texto = notificaciones._armar(
            "compra_acreditada", {"producto": "informe_natal", "medio": "pix"}, lang, "u",
        )
        assert "Ebanx" in texto
