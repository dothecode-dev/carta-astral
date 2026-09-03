"""`GET /api/catalogo/`: qué se vende y a cuánto, para la página de precios.

Público a propósito: quien llega de Instagram tiene que poder ver los precios
antes de crearse una cuenta. Y es la ÚNICA fuente del precio —la misma que el
webhook usa para validar lo que Stripe cobró—, así que la web no puede
anunciar un número distinto del que se cobra: el pack de 5 ya cambió de precio
una vez.

No devuelve textos: los nombres y descripciones viven en el i18n de la web,
traducidos a tres idiomas. Acá van los datos.
"""

import pytest

from api.catalogo import producto

pytestmark = pytest.mark.django_db

URL = "/api/catalogo/"


def test_se_puede_ver_sin_cuenta(client):
    """El visitante frío ve los precios antes de registrarse."""
    assert client.get(URL).status_code == 200


def test_lista_los_tres_productos_de_pago(client):
    codigos = [p["codigo"] for p in client.get(URL).json()["productos"]]

    assert codigos == ["informe_natal", "pack_3_natal", "pack_5_natal"]


def test_no_lista_lo_que_es_gratis(client):
    """La lectura breve no se vende: ofrecerla en la tienda sería cobrar por
    algo que ya viene incluido."""
    codigos = [p["codigo"] for p in client.get(URL).json()["productos"]]

    assert "lectura_breve" not in codigos


def test_el_precio_es_el_del_catalogo(client):
    """Si esto se desincroniza, la web anuncia un precio y Stripe cobra otro."""
    productos = {p["codigo"]: p for p in client.get(URL).json()["productos"]}

    for codigo, datos in productos.items():
        assert datos["precio_centavos"] == producto(codigo).precio_centavos


def test_dice_cuantos_informes_deja_cada_pack(client):
    """Es la diferencia entre "US$ 125" y "US$ 125 por cinco informes"."""
    productos = {p["codigo"]: p for p in client.get(URL).json()["productos"]}

    assert productos["informe_natal"]["otorga"] == [
        {"codigo": "informe_natal", "cantidad": 1},
    ]
    assert productos["pack_5_natal"]["otorga"] == [
        {"codigo": "informe_natal", "cantidad": 5},
    ]


def test_no_expone_nada_mas_que_lo_necesario(client):
    """Un endpoint público no filtra el modelo entero: sólo lo que la página
    de precios necesita para mostrar y para comprar."""
    for p in client.get(URL).json()["productos"]:
        assert set(p) == {"codigo", "precio_centavos", "moneda", "otorga"}


def test_viene_ordenado_de_menor_a_mayor(client):
    precios = [p["precio_centavos"] for p in client.get(URL).json()["productos"]]

    assert precios == sorted(precios)
