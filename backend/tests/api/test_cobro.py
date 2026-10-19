"""`api/cobro.py`: acreditar y reembolsar sin saber de pasarelas. Superficie de PLATA.

Las filas se arman a mano, como las deja el checkout de Mercado Pago: sin HTTP
y sin webhook. Lo que se prueba es el núcleo que el webhook (Task 7) va a
llamar: las mismas garantías que `webhooks_stripe._entregar` +
`_otorgar_y_marcar` y `_reembolsar`.

Los de concurrencia sólo corren contra Postgres: en SQLite `SELECT ... FOR
UPDATE` se ignora y un verde no prueba nada.
"""

import pytest

from api import cobro, compra_service, interpretation_service
from api.models import (
    Account, Derecho, Interpretation, MailBloqueado, Movimiento, PasarelaCheckout, ProviderIdentity, Reembolso,
)
from api.sujetos import sujeto_natal
from tests.api.concurrencia import en_hilos, requiere_postgres

#: Un precio en pesos que no se parece a ningún otro de los tests.
PRECIO_ARS = 1_850_000
CHECKOUT = "mp_test_cobro"


@pytest.fixture
def avisos(monkeypatch):
    enviados = []
    monkeypatch.setattr(cobro, "avisar_admin", enviados.append)
    return enviados


@pytest.fixture
def mails(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        cobro.notificaciones, "notificar",
        lambda cuenta, evento, contexto, lang: enviados.append((cuenta.pk, evento, contexto, lang)),
    )
    return enviados


@pytest.fixture
def eventos(monkeypatch):
    medidos = []
    monkeypatch.setattr(
        cobro.analitica, "evento", lambda cuenta, nombre, props: medidos.append((cuenta.pk, nombre, props)),
    )
    return medidos


@pytest.fixture
def sin_hilo(monkeypatch):
    arrancados = []
    monkeypatch.setattr(
        interpretation_service, "arrancar_en_hilo",
        lambda interpretacion, account: arrancados.append(interpretacion),
    )
    return arrancados


def _fila(cuenta, carta=None, **campos) -> PasarelaCheckout:
    datos = dict(
        checkout_id=CHECKOUT, account=cuenta, codigo_producto="informe_natal",
        sujeto=sujeto_natal(carta) if carta is not None else None,
        pasarela=PasarelaCheckout.MERCADOPAGO, moneda="ars", precio_centavos=PRECIO_ARS,
        mp_preferencia_id="pref_1", locale="pt",
    )
    datos.update(campos)
    return PasarelaCheckout.objects.create(**datos)


def _acreditar(fila, pago_id="111", monto=PRECIO_ARS, moneda="ars", medio="account_money"):
    return cobro.acreditar(
        fila, pago_id=pago_id, monto_pagado=monto, moneda=moneda, medio=medio,
        external_id=f"mp:payment:{pago_id}",
    )


def _reembolsar(fila, refund_id="900", monto=PRECIO_ARS, moneda="ars", pago_id="111"):
    return cobro.reembolsar(
        fila, pago_id=pago_id, refund_id=refund_id, monto=monto, moneda=moneda,
        external_id=f"mp:refund:{refund_id}",
    )


# --- acreditar -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_acreditar_otorga_y_marca_la_fila(make_account, avisos, mails, eventos):
    cuenta = make_account()
    fila = _fila(cuenta)

    assert _acreditar(fila) is True

    fila.refresh_from_db()
    assert fila.payment_intent == "111"
    assert fila.acreditado_at is not None
    assert Movimiento.objects.filter(external_id="mp:payment:111", tipo="otorgamiento").count() == 1
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert eventos == [(cuenta.pk, "compra_completada", {
        "producto": "informe_natal", "monto_centavos": PRECIO_ARS, "locale": "pt",
        "cupon": None, "moneda": "ars", "pasarela": "mercadopago",
    })]
    # Sin carta no hay informe que arrancar: el genérico, en el idioma de la compra.
    assert mails == [(cuenta.pk, "compra_acreditada", {"producto": "informe_natal", "medio": "account_money"}, "pt")]
    assert avisos == []


@pytest.mark.django_db
def test_acreditar_dos_veces_un_movimiento_un_mail(make_account, avisos, mails, eventos):
    """Review Focus 2: el mismo pago notificado otra vez (reintento,
    `payment.updated`) no otorga ni avisa de nuevo, pero la fila queda marcada."""
    cuenta = make_account()
    fila = _fila(cuenta)

    assert _acreditar(fila) is True
    assert _acreditar(PasarelaCheckout.objects.get(pk=fila.pk)) is False

    assert Movimiento.objects.filter(external_id="mp:payment:111").count() == 1
    assert len(mails) == 1
    assert len(eventos) == 1
    fila.refresh_from_db()
    assert fila.payment_intent == "111" and fila.acreditado_at is not None


@pytest.mark.django_db
def test_acreditar_moneda_distinta_no_acredita_y_avisa(make_account, avisos, mails):
    cuenta = make_account()
    fila = _fila(cuenta)

    assert _acreditar(fila, moneda="usd") is False

    assert not Movimiento.objects.filter(account=cuenta, tipo="otorgamiento", origen="compra").exists()
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert len(avisos) == 1 and "usd" in avisos[0] and "ars" in avisos[0]
    assert mails == []


@pytest.mark.django_db
def test_acreditar_monto_distinto_no_acredita_y_avisa(make_account, avisos, mails):
    """Review Focus 4: alguien editó la preferencia, o el catálogo cambió con
    preferencias vivas. Manda el precio congelado en la fila."""
    cuenta = make_account()
    fila = _fila(cuenta)

    assert _acreditar(fila, monto=PRECIO_ARS - 100) is False

    assert not Movimiento.objects.filter(external_id="mp:payment:111").exists()
    fila.refresh_from_db()
    assert fila.acreditado_at is None and fila.payment_intent == ""
    assert len(avisos) == 1 and str(PRECIO_ARS - 100) in avisos[0]
    assert mails == []


@pytest.mark.django_db
def test_acreditar_sin_cuenta_adjudica_por_mail_comprador(make_chart, avisos, mails, sin_hilo):
    carta = make_chart(account=None)
    fila = _fila(None, carta, anonimo=True, nonce_hash="x" * 64, mail_comprador="ana@example.com")

    assert _acreditar(fila) is True

    fila.refresh_from_db()
    assert fila.account is not None
    assert ProviderIdentity.objects.get(provider="email", sub="ana@example.com").account_id == fila.account_id
    assert Movimiento.objects.filter(account=fila.account, external_id="mp:payment:111").count() == 1
    assert mails[0][0] == fila.account_id
    assert avisos == []


@pytest.mark.django_db
def test_acreditar_sin_cuenta_con_mail_bloqueado_acredita_y_avisa(make_chart, avisos, mails, sin_hilo):
    """R8: la plata entró, se entrega igual; pero se mira. El mail va enmascarado."""
    MailBloqueado.bloquear("ana@example.com", motivo="disputa")
    fila = _fila(None, make_chart(account=None), anonimo=True, nonce_hash="x" * 64, mail_comprador="ana@example.com")

    assert _acreditar(fila) is True

    assert len(avisos) == 1 and "BLOQUEADO" in avisos[0]
    assert "ana@example.com" not in avisos[0]


@pytest.mark.django_db
def test_acreditar_sin_cuenta_y_sin_mail_no_otorga_avisa_y_levanta(make_chart, avisos, mails):
    """Ruling 3: una compra sin cuenta pagada en MP sin `mail_comprador` (el
    checkout lo exige) no tiene a quién adjudicarse. Se levanta para que el
    webhook responda 5xx y quede a la vista."""
    fila = _fila(None, make_chart(account=None), anonimo=True, nonce_hash="x" * 64, mail_comprador="")

    with pytest.raises(cobro.CompraAnonimaSinMail):
        _acreditar(fila)

    assert not Movimiento.objects.filter(external_id="mp:payment:111").exists()
    assert Account.objects.count() == 0
    assert len(avisos) == 1
    assert mails == []


@pytest.mark.django_db
def test_acreditar_con_disputa_en_la_fila_levanta(make_account, avisos, mails):
    cuenta = make_account()
    fila = _fila(cuenta, disputa_id="cb_1")

    with pytest.raises(cobro.CompraDisputada):
        _acreditar(fila)

    assert not Movimiento.objects.filter(external_id="mp:payment:111").exists()
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert mails == []


@pytest.mark.django_db
def test_acreditar_arranca_el_informe_de_la_carta(make_account, make_chart, mails, sin_hilo):
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    fila = _fila(cuenta, carta)

    assert _acreditar(fila, medio="credit_card") is True

    assert Interpretation.objects.filter(sujeto__natal_de=carta).count() == 1
    assert len(sin_hilo) == 1
    assert mails == [(cuenta.pk, "informe_en_curso", {"producto": "informe_natal", "medio": "credit_card"}, "pt")]


@pytest.mark.django_db
def test_si_el_informe_no_arranca_la_excepcion_sube_y_el_mail_sale_igual(
    make_account, make_chart, mails, monkeypatch,
):
    """El caller responde 5xx y MP reintenta; la plata ya quedó acreditada y
    el reintento es idempotente. El mail sale una vez, el genérico."""
    cuenta = make_account()
    fila = _fila(cuenta, make_chart(account=cuenta))

    def explota(*_a, **_k):
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(cobro, "arrancar_informe", explota)

    with pytest.raises(RuntimeError):
        _acreditar(fila)

    assert Movimiento.objects.filter(external_id="mp:payment:111").count() == 1
    assert [m[1] for m in mails] == ["compra_acreditada"]

    # El reintento: no otorga de nuevo ni manda otro mail, y vuelve a intentar el arranque.
    monkeypatch.setattr(cobro, "arrancar_informe", compra_service.arrancar_informe)
    monkeypatch.setattr(interpretation_service, "arrancar_en_hilo", lambda *_a: None)
    assert _acreditar(PasarelaCheckout.objects.get(pk=fila.pk)) is False
    assert Interpretation.objects.filter(sujeto=fila.sujeto).count() == 1
    assert len(mails) == 1


@pytest.mark.django_db
def test_si_el_informe_no_arranca_tras_acreditar_avisa_una_vez(make_account, make_chart, mails, avisos, monkeypatch):
    """MP no reintenta tarde y el cron no vuelve a mirar una fila acreditada
    y cerrada: el aviso es la red. Sólo en la llamada que acreditó."""
    cuenta = make_account()
    fila = _fila(cuenta, make_chart(account=cuenta))

    def explota(*_a, **_k):
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(cobro, "arrancar_informe", explota)

    with pytest.raises(RuntimeError):
        _acreditar(fila)
    with pytest.raises(RuntimeError):
        _acreditar(PasarelaCheckout.objects.get(pk=fila.pk))

    assert len(avisos) == 1
    assert "111" in avisos[0] and fila.checkout_id in avisos[0] and "informe" in avisos[0]


@pytest.mark.django_db
def test_el_mismo_pago_tras_rendirse_el_informe_no_lo_rearranca(
    make_account, make_chart, mails, avisos, eventos, sin_hilo,
):
    """Code review A: el informe arrancó, se rindió (INTENTOS_MAXIMOS: se borra
    y el derecho se devuelve) y después llega otra notificación del MISMO pago
    (`payment.updated` por un reembolso parcial, un cambio de estado,
    `acreditar_pago`). No se crea otro informe, no se consume el derecho
    devuelto, no sale mail ni evento ni aviso."""
    from api.canje import devolver

    cuenta = make_account()
    fila = _fila(cuenta, make_chart(account=cuenta))
    assert _acreditar(fila) is True
    fila.refresh_from_db()
    assert fila.informe_arrancado_at is not None

    # Lo que hace `completar_generacion` al rendirse.
    interpretacion = Interpretation.objects.get(sujeto=fila.sujeto)
    devolver(
        cuenta, "informe_natal", external_id=f"informe:{interpretacion.pk}:devolucion",
        sujeto=fila.sujeto, note="test: rendido",
    )
    interpretacion.delete()
    restante = Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante
    mails.clear(), eventos.clear(), sin_hilo.clear()

    assert _acreditar(PasarelaCheckout.objects.get(pk=fila.pk)) is False

    assert not Interpretation.objects.filter(sujeto=fila.sujeto).exists()
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == restante
    assert mails == [] and eventos == [] and sin_hilo == [] and avisos == []


@pytest.mark.django_db
def test_el_mismo_pago_ya_arrancado_no_vuelve_a_adjudicar(make_chart, avisos, mails, sin_hilo, monkeypatch):
    """Una compra sin cuenta ya acreditada y arrancada: la repetición no vuelve
    a pasar por la adjudicación (ni por su aviso de mail bloqueado)."""
    carta = make_chart(account=None)
    fila = _fila(None, carta, anonimo=True, mail_comprador="quien@example.com")
    assert _acreditar(fila) is True
    llamadas = []
    monkeypatch.setattr(cobro, "_adjudicar_si_es_anonima", llamadas.append)

    assert _acreditar(PasarelaCheckout.objects.get(pk=fila.pk)) is False

    assert llamadas == []


@pytest.mark.django_db
def test_arranque_legitimo_sin_informe_tambien_marca(make_account, mails):
    """Sin carta `arrancar_informe` devuelve False sin fallar: eso también es
    «arrancado» —no hay nada que reintentar—."""
    cuenta = make_account()
    fila = _fila(cuenta)
    assert _acreditar(fila) is True
    fila.refresh_from_db()
    assert fila.informe_arrancado_at is not None


@pytest.mark.django_db
def test_arranque_fallido_no_marca(make_account, make_chart, mails, avisos, monkeypatch):
    cuenta = make_account()
    fila = _fila(cuenta, make_chart(account=cuenta))

    def explota(*_a, **_k):
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(cobro, "arrancar_informe", explota)
    with pytest.raises(RuntimeError):
        _acreditar(fila)
    fila.refresh_from_db()
    assert fila.acreditado_at is not None and fila.informe_arrancado_at is None


@pytest.mark.django_db
def test_otro_pago_sobre_una_fila_acreditada_levanta_pago_duplicado(make_account, avisos, mails, eventos):
    """Ruling 1 (RF11b): dos pagos aprobados sobre la misma preferencia de MP
    existen (medido en sandbox). El segundo no otorga: el caller lo reembolsa."""
    cuenta = make_account()
    fila = _fila(cuenta)
    assert _acreditar(fila, pago_id="111") is True

    with pytest.raises(cobro.PagoDuplicado) as exc:
        _acreditar(PasarelaCheckout.objects.get(pk=fila.pk), pago_id="222")

    assert exc.value.pago_id == "222"
    assert Movimiento.objects.filter(account=cuenta, tipo="otorgamiento", origen="compra").count() == 1
    assert not Movimiento.objects.filter(external_id="mp:payment:222").exists()
    fila.refresh_from_db()
    assert fila.payment_intent == "111"
    assert len(mails) == 1 and len(eventos) == 1


@pytest.mark.django_db
def test_pago_sobre_una_fila_vencida_se_acredita_y_avisa(make_account, avisos, mails):
    """EC15: un pago que llega después de que la fila venció. La plata manda."""
    from django.utils import timezone

    cuenta = make_account()
    fila = _fila(cuenta, vencido_at=timezone.now())

    assert _acreditar(fila) is True

    assert len(avisos) == 1 and "vencida" in avisos[0]


# --- reembolsar ----------------------------------------------------------------------------


@pytest.fixture
def acreditada(make_account, mails, eventos, avisos):
    cuenta = make_account()
    fila = _fila(cuenta)
    assert _acreditar(fila) is True
    return PasarelaCheckout.objects.get(pk=fila.pk)


@pytest.mark.django_db
def test_reembolso_total_revoca(acreditada, avisos):
    _reembolsar(acreditada)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="revocacion", external_id="mp:refund:900").count() == 1
    r = Reembolso.objects.get()
    assert (r.refund_id, r.fila_id, r.monto, r.unidades) == ("mp:refund:900", acreditada.pk, PRECIO_ARS, 1)
    acreditada.refresh_from_db()
    assert acreditada.reembolsado_centavos == PRECIO_ARS
    assert acreditada.unidades_revocadas == 1
    assert avisos == []


@pytest.mark.django_db
def test_reembolso_repetido_no_revoca_dos_veces(acreditada):
    _reembolsar(acreditada)
    _reembolsar(PasarelaCheckout.objects.get(pk=acreditada.pk))

    assert Movimiento.objects.filter(tipo="revocacion").count() == 1
    assert Reembolso.objects.count() == 1
    acreditada.refresh_from_db()
    assert acreditada.reembolsado_centavos == PRECIO_ARS
    acreditada.account.refresh_from_db()
    assert acreditada.account.refund_count == 1


@pytest.mark.django_db
def test_reembolso_en_otra_moneda_no_revoca_y_avisa(acreditada, avisos):
    _reembolsar(acreditada, moneda="usd")

    assert not Movimiento.objects.filter(tipo="revocacion").exists()
    assert not Reembolso.objects.exists()
    assert len(avisos) == 1 and "usd" in avisos[0]


@pytest.mark.django_db
def test_reembolso_del_pago_duplicado_no_revoca_la_compra_legitima(acreditada, avisos):
    """Ruling 4: reembolsamos el pago 222 (duplicado de una fila acreditada
    con 111) y MP avisa `refunded` con la misma external_reference. Ese
    reembolso no es de la compra: no puede revocar el informe pagado con 111."""
    _reembolsar(acreditada, refund_id="901", pago_id="222")

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1
    assert not Movimiento.objects.filter(tipo="revocacion").exists()
    assert not Reembolso.objects.exists()
    acreditada.refresh_from_db()
    assert acreditada.reembolsado_centavos == 0 and acreditada.unidades_revocadas == 0
    assert len(avisos) == 1
    assert "reembolso de un pago no acreditado (duplicado)" in avisos[0]
    assert "222" in avisos[0] and "111" in avisos[0] and "mp:refund:901" in avisos[0]


@pytest.mark.django_db
def test_reembolso_sobre_una_fila_sin_acreditar_no_revoca(make_account, avisos):
    """Una fila sin acreditar tiene `payment_intent` vacío: ningún pago es suyo."""
    fila = _fila(make_account())

    _reembolsar(fila, pago_id="111")

    assert not Movimiento.objects.filter(tipo="revocacion").exists()
    assert not Reembolso.objects.exists()
    assert len(avisos) == 1 and "reembolso de un pago no acreditado (duplicado)" in avisos[0]


@pytest.mark.django_db
def test_reembolso_sin_pago_id_no_revoca(make_account, avisos):
    """Un `pago_id` vacío coincidiría con el `payment_intent` vacío de una
    fila sin acreditar: se rechaza antes de mirar la fila."""
    fila = _fila(make_account())

    _reembolsar(fila, pago_id="")

    assert not Movimiento.objects.filter(tipo="revocacion").exists()
    assert not Reembolso.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("pago_id, external_id", [("", "mp:payment:111"), ("111", "")])
def test_acreditar_sin_ids_no_otorga_y_avisa(make_account, avisos, mails, pago_id, external_id):
    """Sin `pago_id` no hay a qué atribuir un reembolso; sin `external_id` el
    primero se guardaría con "" y todos los siguientes se darían por aplicados."""
    cuenta = make_account()
    fila = _fila(cuenta)

    assert cobro.acreditar(
        fila, pago_id=pago_id, monto_pagado=PRECIO_ARS, moneda="ars", medio="x", external_id=external_id,
    ) is False

    assert not Movimiento.objects.filter(account=cuenta, tipo="otorgamiento", origen="compra").exists()
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert len(avisos) == 1
    assert mails == []


# --- concurrencia (sólo Postgres) ----------------------------------------------------------


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_dos_pagos_distintos_a_la_vez_otorgan_uno_solo(make_account, monkeypatch):
    """Ruling 1: dos notificaciones concurrentes de dos pagos aprobados sobre la
    misma fila. Con el chequeo fuera del lock, las dos verían la fila sin
    acreditar y otorgarían dos veces (sus `external_id` son distintos)."""
    monkeypatch.setattr(cobro, "avisar_admin", lambda _t: None)
    monkeypatch.setattr(cobro.notificaciones, "notificar", lambda *_a, **_k: None)
    monkeypatch.setattr(cobro.analitica, "evento", lambda *_a: None)
    cuenta = make_account()
    fila = _fila(cuenta)

    resultados, errores = en_hilos(
        lambda i: _acreditar(PasarelaCheckout.objects.get(pk=fila.pk), pago_id=str(500 + i)), 2,
    )

    assert resultados == [True]
    assert len(errores) == 1 and isinstance(errores[0], cobro.PagoDuplicado), errores
    assert Movimiento.objects.filter(account=cuenta, tipo="otorgamiento", origen="compra").count() == 1
    fila.refresh_from_db()
    assert fila.payment_intent in {"500", "501"}
    assert fila.payment_intent != errores[0].pago_id


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_el_mismo_pago_dos_veces_a_la_vez_otorga_una_sola(make_account, monkeypatch):
    mails = []
    monkeypatch.setattr(cobro, "avisar_admin", lambda _t: None)
    monkeypatch.setattr(cobro.notificaciones, "notificar", lambda *a, **_k: mails.append(a))
    monkeypatch.setattr(cobro.analitica, "evento", lambda *_a: None)
    cuenta = make_account()
    fila = _fila(cuenta)

    resultados, errores = en_hilos(lambda _i: _acreditar(PasarelaCheckout.objects.get(pk=fila.pk)), 3)

    assert not errores, errores
    assert sorted(resultados) == [False, False, True]
    assert Movimiento.objects.filter(external_id="mp:payment:111").count() == 1
    assert len(mails) == 1
