"""Eventos de negocio que el navegador no puede medir.

La web mide lo que pasa en la pantalla (`lib/telemetry`), pero hay un hecho que
ocurre cuando esa pantalla ya no existe: que la plata haya entrado. Stripe lo
confirma por webhook, y quien paga suele cerrar la pestaña —el informe tarda
seis minutos—, así que medirlo desde el navegador dejaría afuera justamente las
compras que más interesa contar.

El `distinct_id` es `str(account.id)`, el mismo que la web pasa a
`posthog.identify()`. Es lo que hace que la visita y la compra sean la misma
persona en el embudo; con cualquier otro identificador se vería tráfico sin
compras y compras sin origen.

Nunca propaga una excepción. Corre después de acreditar: si subiera, el webhook
devolvería 5xx y Stripe reintentaría una compra ya aplicada.

Sale sin consentimiento del banner —que vive en el navegador y acá no llega—
porque una compra es un hecho de negocio, no rastreo publicitario: ya queda
registrada en `Movimiento`. Lo único que la identifica es el id interno de la
cuenta; el mail no viaja, y `test_el_mail_no_viaja` lo fija.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Lista cerrada, por lo mismo que la de la web (`lib/telemetry/events.ts`): con
# nombres libres, en tres meses hay `compra_completada`, `purchase_done` y
# `compra_ok` midiendo lo mismo y ningún embudo cierra.
EVENTOS = ("compra_completada",)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def evento(account, nombre: str, propiedades: dict) -> None:
    if nombre not in EVENTOS:
        raise ValueError(f"evento desconocido: {nombre!r}")
    try:
        _capturar(account, nombre, propiedades)
    except Exception:
        # Con `exception` y no `warning`: que no rompa el cobro no lo vuelve
        # irrelevante — un embudo con agujeros lleva a decidir mal sobre plata.
        logger.exception("no se pudo medir %s de la cuenta %s", nombre, account.pk)


def _capturar(account, nombre, propiedades):
    if not settings.POSTHOG_KEY:
        return
    respuesta = httpx.post(
        f"{settings.POSTHOG_HOST.rstrip('/')}/capture/",
        json={
            "api_key": settings.POSTHOG_KEY,
            "event": nombre,
            # El mismo que `identificar()` en la web: `String(accountId)`.
            "distinct_id": str(account.pk),
            "properties": {**propiedades, "$lib": "astra-backend"},
        },
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
