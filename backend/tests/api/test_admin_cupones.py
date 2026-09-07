"""El admin de cupones: la única superficie de escritura del panel.

Se RENDERIZAN las páginas y se hacen los POST reales, no se mira la
configuración: lo que importa es que un alta publique en Stripe, que un
fallo de Stripe no deje un cupón a medias, que lo inmutable no se pueda
tocar, y que el preview diga el mismo número que después se cobra.
"""
import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.test import Client

from api import canje, stripe_client
from api.cupones import precio_final
from api.models import Account, Cupon, CuponUso, Derecho
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def panel_montado(monkeypatch):
    """Monta el admin en `/panel-test/`, como `admin_montado` en test_admin.py."""
    import importlib

    from django.urls import clear_url_caches

    import config.urls

    monkeypatch.setenv("ADMIN_URL", "panel-test")
    importlib.reload(config.urls)
    clear_url_caches()
    yield
    monkeypatch.delenv("ADMIN_URL", raising=False)
    importlib.reload(config.urls)
    clear_url_caches()


@pytest.fixture(autouse=True)
def config(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    # Mismo motivo que `sin_manifiesto` en test_admin.py: renderizar el admin
    # sin haber corrido collectstatic.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.ALLOWED_HOSTS = ["testserver"]


@pytest.fixture
def stripe_captura(monkeypatch):
    llamadas = {"coupon": [], "promo": [], "modify": []}

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    monkeypatch.setattr(stripe_client.stripe.Price, "retrieve",
                        staticmethod(lambda pid: _Obj(product="prod_" + pid)))
    monkeypatch.setattr(stripe_client.stripe.Coupon, "create",
                        staticmethod(lambda **p: (llamadas["coupon"].append(p), _Obj(id="cup_1"))[1]))
    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "create",
                        staticmethod(lambda **p: (llamadas["promo"].append(p), _Obj(id="promo_1"))[1]))
    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "modify",
                        staticmethod(lambda id, **p: (llamadas["modify"].append((id, p)), _Obj(id=id))[1]))
    return llamadas


@pytest.fixture
def staff():
    c = Client()
    c.force_login(User.objects.create_superuser("staff-cup", "sc@x.com", "pw-de-test-12345"))
    return c


ALTA = "/panel-test/api/cupon/add/"


# El inline de usos viene con su ManagementForm, como en cualquier POST del admin.
INLINE = {"usos-TOTAL_FORMS": "0", "usos-INITIAL_FORMS": "0"}


def datos_alta(**extra):
    base = {
        "codigo": "promo30", "descripcion": "post IG", "porcentaje": "30",
        "productos": ["informe_natal", "pack_5_natal"], "usos_maximos": "100",
        "activo": "on", "vence_el": "2026-09-12",
    }
    base.update(extra)
    return base


def test_el_alta_publica_en_stripe_y_guarda_los_ids(staff, stripe_captura):
    r = staff.post(ALTA, datos_alta())

    assert r.status_code == 302, r.content.decode()[:500]
    c = Cupon.objects.get(codigo="PROMO30")
    assert c.productos == ["informe_natal", "pack_5_natal"]
    assert (c.stripe_coupon_id, c.stripe_promotion_code_id) == ("cup_1", "promo_1")
    assert stripe_captura["promo"][0]["code"] == "PROMO30"


def test_si_stripe_falla_en_el_alta_no_queda_cupon(staff, stripe_captura, monkeypatch):
    def explota(**p):
        raise stripe_client.stripe.StripeError("nope")

    monkeypatch.setattr(stripe_client.stripe.Coupon, "create", staticmethod(explota))

    r = staff.post(ALTA, datos_alta(), follow=True)

    assert Cupon.objects.count() == 0
    assert "stripe" in r.content.decode().lower()


def test_el_100_por_ciento_se_crea_sin_stripe(staff, stripe_captura):
    staff.post(ALTA, datos_alta(codigo="REGALO", porcentaje="100"))

    c = Cupon.objects.get(codigo="REGALO")
    assert c.stripe_promotion_code_id == ""
    assert stripe_captura["coupon"] == []


def test_un_producto_que_no_es_del_catalogo_no_pasa_el_formulario(staff, stripe_captura):
    r = staff.post(ALTA, datos_alta(productos=["no_existe"]))

    assert r.status_code == 200  # se vuelve a mostrar el form con el error
    assert Cupon.objects.count() == 0


def test_el_formulario_de_alta_propone_un_codigo_no_adivinable(staff):
    a = staff.get(ALTA).content.decode()
    b = staff.get(ALTA).content.decode()
    import re

    propuesto = lambda html: re.search(r'name="codigo"[^>]*value="([A-Z0-9-]+)"', html).group(1)  # noqa: E731
    assert propuesto(a) != propuesto(b)
    assert len(propuesto(a)) >= 12


def test_lo_inmutable_no_se_edita_pero_activo_si(staff, stripe_captura):
    c = Cupon.objects.create(codigo="FIJO", porcentaje=30, productos=["informe_natal"],
                             usos_maximos=5, stripe_promotion_code_id="promo_1")

    html = staff.get(f"/panel-test/api/cupon/{c.pk}/change/").content.decode()
    assert 'name="porcentaje"' not in html
    assert 'name="usos_maximos"' not in html
    assert 'name="vence_el"' not in html
    assert 'name="activo"' in html

    staff.post(f"/panel-test/api/cupon/{c.pk}/change/",
               {"descripcion": "apagado por error de %", "activo": "", **INLINE})

    c.refresh_from_db()
    assert c.activo is False
    assert c.descripcion == "apagado por error de %"
    assert stripe_captura["modify"] == [("promo_1", {"active": False})]


def test_si_stripe_no_deja_reactivar_el_cupon_queda_apagado(staff, stripe_captura, monkeypatch):
    def rechaza(id, **p):
        raise stripe_client.stripe.InvalidRequestError("expired", "active")

    monkeypatch.setattr(stripe_client.stripe.PromotionCode, "modify", staticmethod(rechaza))
    c = Cupon.objects.create(codigo="MUERTO", porcentaje=30, productos=["informe_natal"],
                             usos_maximos=1, activo=False, stripe_promotion_code_id="promo_1")

    r = staff.post(f"/panel-test/api/cupon/{c.pk}/change/", {"descripcion": "", "activo": "on", **INLINE}, follow=True)

    c.refresh_from_db()
    assert c.activo is False
    assert "reactivar" in r.content.decode().lower()


def test_el_preview_dice_lo_que_precio_final_dice(staff):
    r = staff.get("/panel-test/api/cupon/precios/", {"porcentaje": "30", "productos": ["informe_natal", "pack_5_natal"]})

    assert r.status_code == 200
    filas = {f["codigo"]: f for f in r.json()["precios"]}
    final, descuento = precio_final(2900, 30)
    assert filas["informe_natal"] == {"codigo": "informe_natal", "lista": 2900, "final": final, "descuento": descuento}
    assert set(filas) == {"informe_natal", "pack_5_natal"}


def test_el_preview_no_es_publico():
    r = Client().get("/panel-test/api/cupon/precios/", {"porcentaje": "30", "productos": ["informe_natal"]})
    assert r.status_code in (302, 403)


def test_el_preview_rechaza_porcentaje_invalido(staff):
    r = staff.get("/panel-test/api/cupon/precios/", {"porcentaje": "0", "productos": ["informe_natal"]})
    assert r.status_code == 400


def test_la_ficha_muestra_los_usos_y_el_preview_con_los_precios(staff):
    c = Cupon.objects.create(codigo="FICHA", porcentaje=30, productos=["informe_natal"], usos_maximos=10)
    acc = Account.objects.create(email="u@x.com")
    CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                            descuento_centavos=870, monto_pagado_centavos=2030,
                            external_id="stripe:session:cs_ficha")

    html = staff.get(f"/panel-test/api/cupon/{c.pk}/change/").content.decode()

    assert "cs_ficha" in html
    assert "20,30" in html  # el precio final, ya dibujado
    listado = staff.get("/panel-test/api/cupon/").content.decode()
    assert "1 / 10" in listado


def test_revocar_un_regalo_del_100_le_saca_el_derecho(staff):
    c = Cupon.objects.create(codigo="REGALO", porcentaje=100, productos=["informe_natal"], usos_maximos=1)
    acc = Account.objects.create(email="r@x.com")
    canje.otorgar(acc, "informe_natal", 1, origen="cupon", external_id="cupon:cupon_abc")
    uso = CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                                  descuento_centavos=2900, monto_pagado_centavos=0,
                                  external_id="cupon:cupon_abc")

    staff.post("/panel-test/api/cuponuso/", {"action": "revocar_regalo", "_selected_action": [uso.pk]})

    uso.refresh_from_db()
    assert uso.revocado_at is not None
    assert Derecho.objects.get(account=acc, codigo_producto="informe_natal").cantidad_restante == 0


def test_revocar_no_aplica_a_un_uso_con_pago(staff):
    c = Cupon.objects.create(codigo="PARCIAL", porcentaje=30, productos=["informe_natal"], usos_maximos=1)
    acc = Account.objects.create(email="p@x.com")
    canje.otorgar(acc, "informe_natal", 1, origen="compra", external_id="stripe:session:cs_p")
    uso = CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                                  descuento_centavos=870, monto_pagado_centavos=2030,
                                  external_id="stripe:session:cs_p")

    staff.post("/panel-test/api/cuponuso/", {"action": "revocar_regalo", "_selected_action": [uso.pk]})

    uso.refresh_from_db()
    assert uso.revocado_at is None
    assert Derecho.objects.get(account=acc, codigo_producto="informe_natal").cantidad_restante == 1


def test_vence_el_se_guarda_como_fecha(staff, stripe_captura):
    staff.post(ALTA, datos_alta())
    assert Cupon.objects.get(codigo="PROMO30").vence_el == dt.date(2026, 9, 12)
