"""El cliente de Polar: abrir una sesión de checkout y traducir sus productos.

Polar es merchant of record: cobra, factura y liquida impuestos, y nos avisa por
webhook. Este módulo sólo habla con su API — quién puede comprar vive en la
vista, y qué se hace con el pago en `api/webhooks_polar.py`.

Usa `httpx` y no `requests`: httpx ya es dependencia del proyecto (viene con el
SDK de Anthropic y está declarada), así que no suma nada nuevo, y su
`MockTransport` deja testear el request de verdad —URL, headers, body— en vez de
comprobar que un mock fue llamado.
"""

import logging

import httpx
from django.conf import settings

from api.catalogo import producto

logger = logging.getLogger(__name__)

# El sandbox es OTRA organización: cuenta, productos y token propios. Apuntar al
# entorno equivocado no da un error claro — o cobra de verdad, o no cobra nada.
_BASE_SANDBOX = "https://sandbox-api.polar.sh/v1"
_BASE_PROD = "https://api.polar.sh/v1"

# Un checkout colgado bloquea un worker de gunicorn, que corre con --timeout 60:
# el arbiter termina matándolo y la persona ve un error después de esperar.
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


# Los idiomas que el sitio sirve. Lista blanca y no concatenación: el locale
# llega del navegador y termina en la URL a la que Polar devuelve a la persona
# después de pagar — sin esta guarda, cualquiera podría fabricar ese destino.
LOCALES = ("es", "en", "pt")
LOCALE_POR_DEFECTO = "es"


class PolarNoConfigurado(Exception):
    """Falta una credencial o el producto no tiene ficha en Polar."""


class PolarError(Exception):
    """Polar respondió algo que no es un checkout.

    Propia y no `httpx.HTTPError` a secas para que la vista pueda distinguirla
    y responder 502 sin dejar un `PolarCheckout` a medias.
    """


def base_url() -> str:
    """El default es producción: un `POLAR_ENVIRONMENT` mal escrito no puede
    mandar los pagos reales al sandbox, que no cobra."""
    if settings.POLAR_ENVIRONMENT == "sandbox":
        return _BASE_SANDBOX
    return _BASE_PROD


def _client() -> httpx.Client:
    """Aislado para poder reemplazar el transporte en los tests."""
    return httpx.Client(timeout=TIMEOUT)


def _id_de_polar(codigo_producto: str) -> str:
    """El id que Polar le puso a ese producto nuestro.

    `settings.POLAR_PRODUCTOS` mapea al revés (id de Polar → código nuestro)
    porque así lo consume el webhook, que es quien recibe el id.
    """
    for id_polar, codigo in settings.POLAR_PRODUCTOS.items():
        if codigo == codigo_producto:
            return id_polar
    # El catálogo y Polar son dos listas que hay que mantener alineadas: mejor
    # fallar acá que abrir un checkout que después nadie puede acreditar.
    raise PolarNoConfigurado(f"{codigo_producto} no tiene ficha en Polar")


def codigo_de_producto(id_polar: str) -> str:
    """Traduce el `product_id` de una orden al código del catálogo.

    Lo usa el webhook. Un id que no mapeamos levanta `KeyError` y esa orden se
    descarta: acreditar "algo" ante un producto desconocido es peor que no
    acreditar nada.
    """
    try:
        return settings.POLAR_PRODUCTOS[id_polar]
    except KeyError:
        raise KeyError(f"producto de Polar desconocido: {id_polar}") from None


def crear_checkout(
    account, codigo_producto: str, chart=None, locale: str = LOCALE_POR_DEFECTO,
) -> tuple[str, str]:
    """Abre una sesión de pago para ese producto y devuelve `(checkout_id, url)`.

    `KeyError` si el producto no está en el catálogo, `ValueError` si es gratis
    y `PolarNoConfigurado` si falta el token o la ficha en Polar: los tres son
    errores de configuración nuestra, no del comprador.

    La `metadata` viaja como respaldo. La relación que manda es
    `PolarCheckout`, porque la propagación de `metadata` del checkout a la orden
    no está en el contrato publicado de Polar (se confirmó leyendo su fuente,
    que puede cambiar); `order.checkout_id` sí está garantizado.
    """
    prod = producto(codigo_producto)  # KeyError si no existe: lo dice el catálogo
    if prod.precio_centavos == 0:
        raise ValueError(f"{codigo_producto} es gratis: no se cobra por Polar")
    if not settings.POLAR_ACCESS_TOKEN:
        raise PolarNoConfigurado("POLAR_ACCESS_TOKEN no configurado")

    cuerpo: dict = {
        "products": [_id_de_polar(codigo_producto)],
        "metadata": {"account_id": str(account.pk)},
    }
    if settings.POLAR_SUCCESS_URL:
        # Quien compra navegando en inglés vuelve a una página en inglés. La
        # variable es una plantilla con `{locale}` porque el idioma lo sabe el
        # navegador, no la configuración; si no lo trae, se usa el default.
        idioma = locale if locale in LOCALES else LOCALE_POR_DEFECTO
        cuerpo["success_url"] = settings.POLAR_SUCCESS_URL.replace("{locale}", idioma)
    if chart is not None:
        cuerpo["metadata"]["chart_id"] = str(chart.pk)

    try:
        with _client() as client:
            resp = client.post(
                f"{base_url()}/checkouts/",
                json=cuerpo,
                headers={"Authorization": f"Bearer {settings.POLAR_ACCESS_TOKEN}"},
            )
    except httpx.HTTPError as exc:
        logger.exception("no se pudo abrir el checkout de %s", codigo_producto)
        raise PolarError(str(exc)) from exc

    if resp.status_code >= 400:
        # El cuerpo puede traer el motivo, pero también el detalle de una
        # credencial: se loguea el status y el producto, no la respuesta cruda.
        logger.error(
            "polar rechazó el checkout: producto=%s status=%s", codigo_producto, resp.status_code
        )
        raise PolarError(f"polar respondió {resp.status_code}")

    datos = resp.json()
    return datos["id"], datos["url"]
