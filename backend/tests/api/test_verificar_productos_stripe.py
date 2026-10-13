import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.management.commands import verificar_productos_stripe as cmd


class _Product(dict):
    def __getattr__(self, k):
        return self[k]


@pytest.fixture
def stripe_productos(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    catalogo = {
        "prod_natal": _Product(id="prod_natal", active=True, tax_code="txcd_10503000", metadata={"codigo_producto": "informe_natal"}),
    }
    monkeypatch.setattr(cmd.stripe.Product, "retrieve", staticmethod(lambda pid: catalogo[pid]))
    return catalogo


def test_todo_bien_no_falla(stripe_productos, capsys):
    call_command("verificar_productos_stripe")
    assert "informe_natal" in capsys.readouterr().out


def test_metadata_distinta_falla(stripe_productos):
    stripe_productos["prod_natal"]["metadata"] = {"codigo_producto": "otro"}
    with pytest.raises(CommandError):
        call_command("verificar_productos_stripe")


def test_product_inactivo_falla(stripe_productos):
    stripe_productos["prod_natal"]["active"] = False
    with pytest.raises(CommandError):
        call_command("verificar_productos_stripe")


def test_sin_tax_code_elegible_falla(stripe_productos):
    stripe_productos["prod_natal"]["tax_code"] = None
    with pytest.raises(CommandError):
        call_command("verificar_productos_stripe")
