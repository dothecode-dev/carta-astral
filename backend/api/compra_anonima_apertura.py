"""Abrir una compra sin cuenta: la carta sin dueño y su pago, en un átomo.

Vive aparte de `api/compra_anonima.py` a propósito: es lo único de «pagar es
entrar» que necesita una pasarela (por `apertura`), y a `compra_anonima` la
importa `api.cobro` para adjudicar. Con `abrir` adentro, `cobro` llegaba a las
pasarelas por `compra_anonima` → `apertura` → `pasarelas`, y eso armaba el
ciclo que rompía importar primero un submódulo de Mercado Pago y obligaba a
aflojar el contrato «cobro no conoce pasarelas» de import-linter.
"""

import secrets

from django.db import transaction

from api import apertura
from api.chart_service import create_chart
from api.compra_anonima import PRODUCTO, comprobar_disponible
from api.identity import hash_token, normalizar
from api.sujetos import sujeto_natal


def abrir(datos: dict, locale: str, moneda: str = "usd", email: str = ""):
    """Crea la carta sin dueño, abre el pago y guarda la fila (`apertura`).

    Devuelve `(fila, nonce_en_claro)`; en la base sólo queda el hash del nonce.
    `datos` ya viene validado por la vista. La carta y la apertura del pago van
    en el mismo átomo para que un fallo de la pasarela no deje una carta sin
    dueño; una sesión huérfana (si la base falla después) vence sola a la hora.

    Sin cupón, siempre al precio de lista (review 07-10): sin cuenta no se
    puede aplicar «uno por cuenta», y la adjudicación podía llevar la compra
    a una cuenta que ya lo había usado. La vista rechaza cualquier cupón
    antes de llegar acá. `moneda` ya viene validada contra el producto.

    En pesos (Mercado Pago) `email` es obligatorio y ya viene validado: MP no
    devuelve el mail de quien pagó (es el de su cuenta de MP, que puede ser de
    un pariente), así que el que se pidió acá es el que recibe el código.
    """
    comprobar_disponible()
    nonce = secrets.token_urlsafe(32)
    with transaction.atomic():
        carta = create_chart(datos, account=None)
        sujeto = sujeto_natal(carta)
        fila = apertura.abrir_checkout(
            None, PRODUCTO, sujeto=sujeto, locale=locale, moneda=moneda,
            mail=normalizar(email), anonimo=True, nonce_hash=hash_token(nonce),
        )
    return fila, nonce
