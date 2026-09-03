import pytest

from api.canje import MontoInvalido, aplicar_compra
from api.catalogo import producto
from api.models import Derecho, Movimiento

# Del catálogo y no un literal: el precio cambia (el pack de 5 pasó de
# US$ 149,90 a US$ 125,00 el 02-09-2026) y estos tests son sobre qué otorga
# la compra, no sobre cuánto sale. El valor exacto lo fija test_catalogo.py.
PRECIO_PACK = producto("pack_5_natal").precio_centavos

pytestmark = pytest.mark.django_db


def test_una_compra_suelta_otorga_uno_y_lo_canjea_contra_la_carta(make_account, make_chart):
    cuenta = make_account()
    carta = make_chart(account=cuenta)

    aplicar_compra(cuenta, "informe_natal", 2900, external_id="polar:1", chart=carta)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="consumo", chart=carta).count() == 1


def test_el_pack_otorga_cinco_y_no_canjea_nada(make_account):
    cuenta = make_account()

    aplicar_compra(cuenta, "pack_5_natal", PRECIO_PACK, external_id="polar:2")

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 5
    assert Movimiento.objects.filter(tipo="consumo").count() == 0


def test_si_la_carta_ya_no_existe_otorga_igual_y_no_canjea(make_account, make_chart):
    # Compró desde /carta/41 y borró la carta antes de que llegara el webhook.
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    carta_id = carta.id
    carta.delete()

    aplicar_compra(cuenta, "informe_natal", 2900, external_id="polar:3", chart_id=carta_id)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1


def test_un_monto_distinto_al_del_catalogo_se_rechaza(make_account):
    with pytest.raises(MontoInvalido):
        aplicar_compra(make_account(), "informe_natal", 100, external_id="polar:4")


def test_un_monto_mayor_tambien_se_rechaza(make_account):
    with pytest.raises(MontoInvalido):
        aplicar_compra(make_account(), "informe_natal", 5000, external_id="polar:5")


def test_un_monto_menor_con_descuento_declarado_se_acepta(make_account):
    cuenta = make_account()

    aplicar_compra(cuenta, "informe_natal", 2320, external_id="polar:6", descuento_centavos=580)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1


def test_el_rechazo_avisa_con_los_tres_datos(make_account, caplog):
    with pytest.raises(MontoInvalido):
        aplicar_compra(make_account(), "informe_natal", 100, external_id="polar:7")

    assert "informe_natal" in caplog.text and "2900" in caplog.text and "100" in caplog.text


def test_el_mismo_evento_no_se_aplica_dos_veces(make_account):
    cuenta = make_account()
    aplicar_compra(cuenta, "pack_5_natal", PRECIO_PACK, external_id="polar:8")

    assert aplicar_compra(cuenta, "pack_5_natal", PRECIO_PACK, external_id="polar:8") is False

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 5


def test_un_descuento_negativo_se_rechaza(make_account):
    with pytest.raises(MontoInvalido):
        aplicar_compra(
            make_account(), "informe_natal", 3200, external_id="polar:9",
            descuento_centavos=-300,
        )


def test_un_descuento_mayor_al_precio_se_rechaza(make_account):
    with pytest.raises(MontoInvalido):
        aplicar_compra(
            make_account(), "informe_natal", 0, external_id="polar:10",
            descuento_centavos=3000,
        )


def test_el_pack_no_canjea_aunque_llegue_con_carta(make_account, make_chart):
    cuenta = make_account()
    carta = make_chart(account=cuenta)

    aplicar_compra(cuenta, "pack_5_natal", PRECIO_PACK, external_id="polar:11", chart=carta)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 5
    assert Movimiento.objects.filter(tipo="consumo").count() == 0


# --- La frontera transaccional de `aplicar_compra` ---------------------------
#
# Con Stripe, un fallo transitorio se responde 5xx para que la pasarela
# reintente durante tres días (con Polar se respondía 2xx a todo y el error se
# perdía). Ese reintento sólo es seguro si el otorgamiento y el canje son un
# solo átomo: si el canje falla después de otorgar y el otorgamiento queda
# committeado, cada reintento sale por el `return False` del duplicado y quien
# pagó se queda con el derecho puesto y sin informe, para siempre.


def _canje_que_explota(*_args, **_kwargs):
    raise RuntimeError("la base se cayó justo en el canje")


def test_si_el_canje_falla_el_otorgamiento_no_queda_committeado(
    make_account, make_chart, monkeypatch,
):
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    monkeypatch.setattr("api.canje.canjear", _canje_que_explota)

    with pytest.raises(RuntimeError):
        aplicar_compra(
            cuenta, "informe_natal", 2900, external_id="stripe:session:cs_1", chart=carta,
        )

    assert not Movimiento.objects.filter(external_id="stripe:session:cs_1").exists()
    assert not Derecho.objects.filter(codigo_producto="informe_natal").exists()


def test_el_reintento_despues_de_un_canje_fallido_entrega_el_informe(
    make_account, make_chart, monkeypatch,
):
    """El caso que rompe el cobro: la entrega falla en el canje y Stripe reintenta.

    Sin átomo, el `external_id` del primer intento ya está aplicado y el
    reintento sale por el duplicado sin llegar nunca al canje: derecho
    otorgado, informe nunca entregado, y los tres días de reintentos no lo
    arreglan porque todos salen por la misma línea.
    """
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    monkeypatch.setattr("api.canje.canjear", _canje_que_explota)
    with pytest.raises(RuntimeError):
        aplicar_compra(
            cuenta, "informe_natal", 2900, external_id="stripe:session:cs_2", chart=carta,
        )

    monkeypatch.undo()
    assert aplicar_compra(
        cuenta, "informe_natal", 2900, external_id="stripe:session:cs_2", chart=carta,
    ) is True

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="consumo", chart=carta).count() == 1
    assert Movimiento.objects.filter(external_id="stripe:session:cs_2").count() == 1
