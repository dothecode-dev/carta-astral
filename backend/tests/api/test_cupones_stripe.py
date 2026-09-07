"""El espejo de un cupón en Stripe: Coupon + Promotion Code al publicarlo, y
`active` al apagarlo o prenderlo.

Todo por `cupones.publicar` / `cupones.cambiar_activo`, que son lo que el
admin llama. Stripe se captura sin salir a la red, al estilo de
`stripe_responde` en `test_stripe_checkout.py`.
"""
import datetime as dt

import pytest

from api import cupones, stripe_client
from api.models import Cupon


@pytest.fixture(autouse=True)
def stripe_config(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}


@pytest.fixture
def stripe_captura(monkeypatch):
    """Captura las llamadas a Coupon, PromotionCode y Price."""
    llamadas = {"coupon": [], "promo": [], "modify": []}

    class _Obj:
        def __init__(self, id):
            self.id = id

    class _Price:
        def __init__(self, product):
            self.product = product

    def price_retrieve(price_id):
        return _Price({"price_natal": "prod_natal", "price_pack": "prod_pack"}[price_id])

    def coupon_create(**p):
        llamadas["coupon"].append(p)
        return _Obj("cup_1")

    def promo_create(**p):
        llamadas["promo"].append(p)
        return _Obj("promo_1")

    def promo_modify(id, **p):
        llamadas["modify"].append((id, p))
        return _Obj(id)

    monkeypatch.setattr(stripe_client.stripe.Price, "retrieve", staticmethod(price_retrieve))
    monkeypatch.setattr(stripe_client.stripe.Coupon, "create", staticmethod(coupon_create))
    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "create", staticmethod(promo_create))
    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "modify", staticmethod(promo_modify))
    return llamadas


def nuevo(**campos):
    base = dict(codigo="PROMO30", porcentaje=30, productos=["informe_natal", "pack_5_natal"],
                usos_maximos=100, vence_el=dt.date(2026, 9, 12))
    base.update(campos)
    return Cupon.objects.create(**base)


@pytest.mark.django_db
def test_publicar_crea_coupon_y_promotion_code_con_lo_que_el_cupon_dice(stripe_captura):
    c = nuevo()

    cupones.publicar(c)

    (coupon,) = stripe_captura["coupon"]
    assert coupon["percent_off"] == 30
    assert coupon["duration"] == "once"
    assert coupon["max_redemptions"] == 100
    assert coupon["applies_to"] == {"products": ["prod_natal", "prod_pack"]}
    assert coupon["redeem_by"] == int(c.vence_at.timestamp())
    (promo,) = stripe_captura["promo"]
    assert promo["promotion"] == {"type": "coupon", "coupon": "cup_1"}
    assert promo["code"] == "PROMO30"
    assert promo["max_redemptions"] == 100
    assert promo["expires_at"] == int(c.vence_at.timestamp())
    assert promo["metadata"]["cupon_id"] == str(c.pk)
    c.refresh_from_db()
    assert (c.stripe_coupon_id, c.stripe_promotion_code_id) == ("cup_1", "promo_1")


@pytest.mark.django_db
def test_sin_vencimiento_no_se_manda_fecha(stripe_captura):
    cupones.publicar(nuevo(vence_el=None))

    assert "redeem_by" not in stripe_captura["coupon"][0]
    assert "expires_at" not in stripe_captura["promo"][0]


@pytest.mark.django_db
def test_el_100_por_ciento_no_toca_stripe(stripe_captura):
    c = nuevo(porcentaje=100)

    cupones.publicar(c)

    assert stripe_captura["coupon"] == [] and stripe_captura["promo"] == []
    assert (c.stripe_coupon_id, c.stripe_promotion_code_id) == ("", "")


@pytest.mark.django_db
def test_publicar_dos_veces_no_crea_dos(stripe_captura):
    c = nuevo()
    cupones.publicar(c)
    cupones.publicar(c)
    assert len(stripe_captura["coupon"]) == 1


@pytest.mark.django_db
def test_si_stripe_falla_el_cupon_no_queda_publicado(monkeypatch, stripe_captura):
    def explota(**p):
        raise stripe_client.stripe.StripeError("nope")

    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "create", staticmethod(explota))
    c = nuevo()

    with pytest.raises(stripe_client.StripeError):
        cupones.publicar(c)

    c.refresh_from_db()
    assert c.stripe_promotion_code_id == ""


@pytest.mark.django_db
def test_desactivar_apaga_en_stripe_antes_de_guardar(stripe_captura):
    c = nuevo(stripe_promotion_code_id="promo_1")

    cupones.cambiar_activo(c, False)

    assert stripe_captura["modify"] == [("promo_1", {"active": False})]
    c.refresh_from_db()
    assert c.activo is False


@pytest.mark.django_db
def test_si_stripe_no_deja_reactivar_el_cupon_sigue_apagado(monkeypatch, stripe_captura):
    """Agotado o vencido, Stripe lo deja «permanently inactive»."""
    def rechaza(id, **p):
        raise stripe_client.stripe.InvalidRequestError("expired", "active")

    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "modify", staticmethod(rechaza))
    c = nuevo(activo=False, stripe_promotion_code_id="promo_1")

    with pytest.raises(cupones.NoSePuedeReactivar):
        cupones.cambiar_activo(c, True)

    c.refresh_from_db()
    assert c.activo is False


@pytest.mark.django_db
def test_el_100_por_ciento_se_apaga_y_prende_sin_stripe(stripe_captura):
    c = nuevo(porcentaje=100)
    cupones.cambiar_activo(c, False)
    cupones.cambiar_activo(c, True)
    assert stripe_captura["modify"] == []
    c.refresh_from_db()
    assert c.activo is True
