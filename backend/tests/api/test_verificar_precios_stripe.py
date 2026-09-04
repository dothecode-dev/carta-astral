"""`manage.py verificar_precios_stripe`: que el catálogo y Stripe digan lo mismo.

El comando existe porque el 04-09-2026 los tres precios live estaban en
`tax_behavior: unspecified` y nadie lo sabía: cobraban bien de casualidad,
porque el default de la cuenta era `inclusive`. Estos tests cubren lo que el
comando tiene que detectar, que es justamente lo que ningún otro gate ve —el
webhook valida el subtotal, y el subtotal no cambia con el impuesto—.
"""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

CATALOGO_COMPLETO = {
    "price_natal": "informe_natal",
    "price_3": "pack_3_natal",
    "price_5": "pack_5_natal",
}
MONTOS = {"informe_natal": 2900, "pack_3_natal": 7900, "pack_5_natal": 12500}


class _Precio:
    def __init__(self, monto, tax_behavior="inclusive", active=True):
        self.unit_amount = monto
        self.currency = "usd"
        self.tax_behavior = tax_behavior
        self.active = active


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = dict(CATALOGO_COMPLETO)


@pytest.fixture
def stripe_dice(monkeypatch):
    """Lo que responde Stripe, por price_id. Sin red."""
    from api.management.commands import verificar_precios_stripe as cmd  # noqa: F401
    import stripe

    precios = {pid: _Precio(MONTOS[cod]) for pid, cod in CATALOGO_COMPLETO.items()}
    modificados = []

    def retrieve(price_id):
        try:
            return precios[price_id]
        except KeyError:
            raise ValueError(f"No such price: {price_id!r}") from None

    def modify(price_id, **campos):
        modificados.append((price_id, campos))
        for k, v in campos.items():
            setattr(precios[price_id], k, v)

    class _Ajustes:
        class defaults:
            tax_behavior = "inclusive"

        status = "active"

    monkeypatch.setattr(stripe.Price, "retrieve", staticmethod(retrieve))
    monkeypatch.setattr(stripe.Price, "modify", staticmethod(modify))
    monkeypatch.setattr(stripe.tax.Settings, "retrieve", staticmethod(lambda: _Ajustes))
    precios["_modificados"] = modificados
    return precios


def _correr(*args):
    salida = io.StringIO()
    call_command("verificar_precios_stripe", *args, stdout=salida, stderr=salida)
    return salida.getvalue()


def test_todo_en_orden_no_falla(stripe_dice):
    salida = _correr()
    assert "coinciden con el catálogo" in salida


def test_precio_distinto_al_catalogo_falla(stripe_dice):
    """El caso caro: la web publica un número y Stripe cobra otro."""
    stripe_dice["price_natal"].unit_amount = 3900
    with pytest.raises(CommandError):
        _correr()


def test_tax_behavior_no_inclusive_falla(stripe_dice):
    """`unspecified` cobra bien sólo mientras el default de la cuenta no cambie."""
    stripe_dice["price_3"].tax_behavior = "unspecified"
    with pytest.raises(CommandError):
        _correr()


def test_precio_inactivo_falla(stripe_dice):
    stripe_dice["price_5"].active = False
    with pytest.raises(CommandError):
        _correr()


def test_producto_del_catalogo_sin_precio_falla(settings, stripe_dice):
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    with pytest.raises(CommandError) as e:
        _correr()
    assert "problema" in str(e.value)


def test_fijar_inclusive_solo_toca_los_unspecified(stripe_dice):
    stripe_dice["price_3"].tax_behavior = "unspecified"
    _correr("--fijar-inclusive")
    assert stripe_dice["_modificados"] == [("price_3", {"tax_behavior": "inclusive"})]
    assert stripe_dice["price_3"].tax_behavior == "inclusive"


def test_fijar_inclusive_no_arregla_un_exclusive(stripe_dice):
    """Stripe no deja cambiarlo una vez puesto: el comando avisa en vez de mentir."""
    stripe_dice["price_5"].tax_behavior = "exclusive"
    with pytest.raises(CommandError):
        _correr("--fijar-inclusive")
    assert stripe_dice["_modificados"] == []


def test_sin_clave_no_corre(settings, stripe_dice):
    settings.STRIPE_SECRET_KEY = ""
    with pytest.raises(CommandError):
        _correr()
