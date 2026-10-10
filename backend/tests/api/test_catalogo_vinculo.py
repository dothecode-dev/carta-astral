import pytest

from api import catalogo
from api.canje import CapacidadAjena, canjear, otorgar
from api.models import Cupon
from api.sujetos import sujeto_natal

pytestmark = pytest.mark.django_db


def test_el_vinculo_esta_en_el_catalogo_a_9_dolares():
    p = catalogo.producto("informe_vinculo")
    assert p.precio_centavos == 900 and p.capacidades == ("leer_vinculo",) and p.sujeto == "vinculo"


@pytest.fixture
def apagado(settings):
    settings.VINCULO_ENABLED = False


def test_apagado_no_esta_a_la_venta(apagado):
    assert "informe_vinculo" not in {p.codigo for p in catalogo.a_la_venta()}
    assert not catalogo.disponible("informe_vinculo")


def test_apagado_no_aparece_en_el_catalogo_publico(apagado, client):
    codigos = {p["codigo"] for p in client.get("/api/catalogo/").json()["productos"]}
    assert "informe_vinculo" not in codigos


def test_apagado_no_es_elegible_en_el_admin_de_cupones(apagado):
    from api.admin import _productos_con_precio
    assert "informe_vinculo" not in {p.codigo for p in _productos_con_precio()}


def test_apagado_verificar_precios_no_lo_pide(apagado):
    from api.management.commands.verificar_precios_stripe import _codigos_vendibles
    assert "informe_vinculo" not in {p.codigo for p in _codigos_vendibles()}


def test_apagado_un_cupon_que_lo_nombra_no_lo_lista(apagado, client):
    Cupon.objects.create(codigo="MITAD", porcentaje=50, productos=["informe_vinculo"], usos_maximos=5)
    productos = client.get("/api/cupones/MITAD/?producto=informe_vinculo").json().get("productos", [])
    assert all(p["codigo"] != "informe_vinculo" for p in productos)


def test_un_cupon_sin_el_producto_no_aplica_al_vinculo(settings):
    """RF20: los cupones nombran sus productos; uno del 100 % sin nombrarlo no aplica."""
    from api import cupones
    settings.VINCULO_ENABLED = True
    Cupon.objects.create(codigo="GRATIS", porcentaje=100, productos=["informe_natal"], usos_maximos=5)
    with pytest.raises(cupones.CuponInvalido):
        cupones.validar("GRATIS", "informe_vinculo")


def test_un_derecho_natal_no_canjea_un_vinculo(make_account):
    from api.models import Sujeto
    acc = make_account(informes=1)
    vinculo = Sujeto.objects.create(producto=Sujeto.VINCULO, account=acc)
    with pytest.raises(CapacidadAjena):
        canjear(acc, "leer_informe", vinculo)


def test_un_derecho_de_vinculo_no_canjea_una_carta(make_account, make_chart):
    acc = make_account()
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="v1")
    with pytest.raises(CapacidadAjena):
        canjear(acc, "leer_vinculo", sujeto_natal(make_chart(acc)))
