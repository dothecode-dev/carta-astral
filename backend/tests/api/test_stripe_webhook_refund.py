"""El reembolso de una compra de Stripe: tests 21-25, 40 y 41 de la spec.

Dos cosas que no son obvias y salieron de incidentes:

- **El evento no trae el id de la sesión.** `refund.created` llega con
  `payment_intent` y `charge`, así que la compra se resuelve por el
  `payment_intent` que guardamos al acreditar. Verificado contra un reembolso
  real en modo test.
- **No se le quita a nadie un informe ya entregado.** `canje.revocar` baja el
  derecho hasta donde alcanza y manda el resto a deuda, que se cancela contra
  la próxima compra.
"""

import json

import pytest

from api.canje import aplicar_compra, canjear
from api.catalogo import producto
from api.models import Account, Derecho, Movimiento, PasarelaCheckout
from api.sujetos import sujeto_natal
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
PI = "pi_reembolso"
REFUND = "re_1"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}


def _entregar(client, refund=None):
    cuerpo = json.dumps({
        "id": "evt_r", "type": "refund.created",
        "data": {"object": refund if refund is not None else _refund()},
    }).encode()
    return client.post(
        URL, data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


def _refund(**cambios) -> dict:
    """La forma exacta que devolvió un `refund.created` real en modo test."""
    refund = {
        "id": REFUND, "object": "refund", "amount": 2900, "currency": "usd",
        "charge": "ch_1", "payment_intent": PI, "reason": None, "status": "succeeded",
    }
    refund.update(cambios)
    return refund


@pytest.fixture
def comprado(make_account, make_chart):
    """Una compra ya acreditada, como la deja el webhook de pago."""
    cuenta = make_account()
    fila = PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_1", account=cuenta, codigo_producto="informe_natal",
        sujeto=sujeto_natal(make_chart(account=cuenta)), pago_id=PI,
    )
    aplicar_compra(cuenta, "informe_natal", 2900, external_id="stripe:session:cs_1")
    return fila


def test_un_reembolso_revoca_lo_comprado(client, comprado):
    r = _entregar(client)

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(
        tipo="revocacion", external_id=f"stripe:refund:{REFUND}",
    ).count() == 1


def test_reembolsar_algo_ya_usado_deja_deuda(client, comprado, make_chart):
    """El informe ya se entregó: no se le saca a nadie, se anota la deuda."""
    canjear(comprado.account, "leer_informe", sujeto_natal(comprado.sujeto.natal_de))

    r = _entregar(client)

    assert r.status_code == 200
    comprado.account.refresh_from_db()
    assert comprado.account.deuda == 1
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


def test_el_reembolso_no_se_descarta_como_duplicado_del_pago(client, comprado):
    """Comparten el pago, no el `external_id`: `stripe:session:` contra
    `stripe:refund:`. Con la misma clave, el reembolso se perdería."""
    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id="stripe:session:cs_1").count() == 1
    assert Movimiento.objects.filter(external_id=f"stripe:refund:{REFUND}").count() == 1


def test_el_mismo_reembolso_dos_veces_revoca_una_sola(client, comprado):
    _entregar(client)
    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(tipo="revocacion").count() == 1
    comprado.account.refresh_from_db()
    assert comprado.account.refund_count == 1


def test_un_reembolso_sin_payment_intent_no_engancha_ninguna_compra(client, make_account):
    """Una compra abierta y todavía sin acreditar tiene el `payment_intent`
    vacío: un filtro por vacío las engancharía a todas y terminaría revocando
    la compra de cualquiera."""
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_abierta", account=make_account(), codigo_producto="informe_natal",
    )

    r = _entregar(client, _refund(payment_intent=None))

    assert r.status_code == 200
    assert not Movimiento.objects.filter(tipo="revocacion").exists()


def test_una_cuenta_borrada_despues_de_comprar_registra_el_movimiento(client, comprado):
    """Un reembolso puede llegar meses después del borrado de la cuenta: no hay
    a quién bajarle el derecho, pero la contabilidad tiene que cerrar."""
    Account.objects.filter(pk=comprado.account.pk).delete()

    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(
        tipo="revocacion", external_id=f"stripe:refund:{REFUND}",
    ).count() == 1


def test_un_reembolso_sin_compra_conocida_pide_reintento(client):
    """El único "no encuentro la compra" que sí se arregla reintentando: el
    reembolso puede llegar antes de que el pago termine de acreditarse."""
    r = _entregar(client)

    assert r.status_code >= 500
    assert not Movimiento.objects.exists()


def test_los_reembolsos_de_la_pasarela_cuentan_para_el_contador(client, comprado):
    """Decidido el 03-09-2026: cuentan todos. El payload no dice quién inició el
    reembolso —`reason` llega vacío— así que distinguirlos sería adivinar, y
    `flagged` no bloquea nada: es una columna del admin para mirar la cuenta."""
    _entregar(client)

    comprado.account.refresh_from_db()
    assert comprado.account.refund_count == 1


# --- Reembolso parcial (test 39) --------------------------------------------
#
# Decidido el 03-09-2026: se revoca la proporción redondeada HACIA ARRIBA. Ante
# la duda no se regala producto, y lo que la persona ya usó no se le saca igual
# —eso va a deuda—. En un producto suelto cualquier reembolso parcial revoca su
# única unidad: no existe medio informe.

PRECIO_PACK = producto("pack_5_natal").precio_en("usd")


@pytest.fixture
def pack_comprado(make_account):
    cuenta = make_account()
    fila = PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_pack", account=cuenta, codigo_producto="pack_5_natal",
        pago_id=PI,
    )
    aplicar_compra(cuenta, "pack_5_natal", PRECIO_PACK, external_id="stripe:session:cs_pack")
    return fila


def test_medio_pack_reembolsado_revoca_tres_de_cinco(client, pack_comprado):
    r = _entregar(client, _refund(amount=PRECIO_PACK // 2))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 2


def test_el_pack_entero_reembolsado_revoca_los_cinco(client, pack_comprado):
    r = _entregar(client, _refund(amount=PRECIO_PACK))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


def test_un_reembolso_parcial_de_un_suelto_revoca_su_unica_unidad(client, comprado):
    r = _entregar(client, _refund(amount=1450))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


def test_un_reembolso_mayor_al_precio_no_revoca_de_mas(client, pack_comprado):
    """Un monto raro no puede inventar unidades: la proporción se acota en 1."""
    r = _entregar(client, _refund(amount=PRECIO_PACK * 3))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    pack_comprado.account.refresh_from_db()
    assert pack_comprado.account.deuda == 0


def test_el_reembolso_queda_anotado_en_la_compra(client, comprado):
    """Para que la cuenta pueda decir «reembolsada» sin sumar movimientos."""
    _entregar(client, _refund(amount=2900))
    _entregar(client, _refund(amount=2900))  # el mismo, reentregado: no suma dos veces

    comprado.refresh_from_db()
    assert comprado.reembolsado_centavos == 2900


def test_dos_reembolsos_parciales_se_suman(client, pack_comprado):
    _entregar(client, _refund(id="re_a", amount=2500))
    _entregar(client, _refund(id="re_b", amount=2500))

    pack_comprado.refresh_from_db()
    assert pack_comprado.reembolsado_centavos == 5000


def test_el_reembolso_se_mide_contra_lo_que_se_pago_no_contra_el_precio_de_hoy(
    client, make_account, monkeypatch,
):
    """Un pack comprado a 12500 y reembolsado a medias, después de que el
    catálogo cambió su precio: contra el precio nuevo, la mitad de lo pagado
    parecería un reembolso total y se revocarían los cinco."""
    import dataclasses

    from api import catalogo

    cuenta = make_account()
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_pack", account=cuenta, codigo_producto="pack_5_natal",
        pago_id=PI, precio_centavos=12500,
    )
    aplicar_compra(cuenta, "pack_5_natal", 12500, external_id="stripe:session:cs_pack")
    monkeypatch.setitem(
        catalogo.CATALOGO, "pack_5_natal",
        dataclasses.replace(catalogo.CATALOGO["pack_5_natal"], precios={"usd": 2500}),
    )

    r = _entregar(client, _refund(amount=6250))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 2


# --- La moneda del reembolso (cobro-brl-pix) ---------------------------------


def test_un_reembolso_en_otra_moneda_no_toca_nada(client, comprado, monkeypatch):
    """Un refund de 2900 `brl` sobre una compra `usd` no son 2900 de nada."""
    from api import cobro

    avisos_ = []
    monkeypatch.setattr(cobro, "avisar", avisos_.append)

    r = _entregar(client, _refund(amount=2900, currency="brl"))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1
    assert not Movimiento.objects.filter(tipo="revocacion").exists()
    assert len(avisos_) == 1
    assert avisos_[0].startswith(f"Reembolso stripe:refund:{REFUND}: vino en brl")


def test_un_reembolso_parcial_en_reales_revoca_por_proporcion(client, make_account):
    """EC9: medio pack pagado en reales revoca 3 de 5, como en dólares. La
    proporción se mide contra lo congelado en la fila, en su moneda."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_pack", account=cuenta, codigo_producto="pack_5_natal",
        pago_id=PI, moneda="brl", precio_centavos=14900,
    )
    aplicar_compra(
        cuenta, "pack_5_natal", 14900, external_id="stripe:session:cs_pack", precio_centavos=14900,
    )

    r = _entregar(client, _refund(amount=7450, currency="brl"))

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 2


def test_reembolso_viejo_reenviado_es_noop(client, comprado):
    """Un reembolso aplicado antes de la 0065 (ya migrado a `stripe:refund:`) y
    reenviado por Stripe no revoca de nuevo ni crea otro `Reembolso`."""
    from api.canje import revocar
    from api.models import Reembolso

    revocar(comprado.account, "informe_natal", 1, external_id=f"stripe:refund:{REFUND}")
    Reembolso.objects.create(refund_id=f"stripe:refund:{REFUND}", fila=comprado, monto=2900, unidades=1)

    r = _entregar(client)

    assert r.status_code == 200
    assert Reembolso.objects.count() == 1
    assert Movimiento.objects.filter(tipo="revocacion").count() == 1


def test_el_reembolso_queda_con_el_id_prefijado(client, comprado):
    from api.models import Reembolso

    _entregar(client)

    assert list(Reembolso.objects.values_list("refund_id", flat=True)) == [f"stripe:refund:{REFUND}"]


def test_sin_fila_pide_reintento(client):
    """Un reembolso de un pago que ninguna fila de Stripe conoce: 5xx, porque el
    reintento sí lo arregla (el pago puede estar acreditándose)."""
    r = _entregar(client, _refund(payment_intent="pi_desconocido"))

    assert r.status_code >= 500
    assert not Movimiento.objects.exists()


def test_reembolso_guardado_con_id_crudo_durante_el_deploy_es_noop(client, comprado):
    """Durante el deploy el contenedor viejo convive con el nuevo y sigue
    guardando `refund_id` crudo (`re_…`) DESPUÉS de que corrió la 0065. Un
    reenvío que llega al código nuevo no puede volver a aplicarlo."""
    from api.canje import revocar
    from api.models import Reembolso

    # Lo que deja el código viejo: revocación, contadores de la fila y constancia cruda.
    revocar(comprado.account, "informe_natal", 1, external_id=f"stripe:refund:{REFUND}")
    PasarelaCheckout.objects.filter(pk=comprado.pk).update(unidades_revocadas=1, reembolsado_centavos=2900)
    Reembolso.objects.create(refund_id=REFUND, fila=comprado, monto=2900, unidades=1)

    r = _entregar(client)

    assert r.status_code == 200
    assert Reembolso.objects.count() == 1
    assert Movimiento.objects.filter(tipo="revocacion").count() == 1
    comprado.refresh_from_db()
    assert comprado.reembolsado_centavos == 2900
