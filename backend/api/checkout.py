"""`POST /api/checkout/`: abre una sesión de pago en Polar.

En módulo propio y no en `api/views.py`, que ya pasó las 250 líneas que el
CLAUDE.md marca como techo — mismo criterio que `api/webhooks.py`.

Lo único que llega del navegador es QUÉ producto se compra y, opcionalmente,
sobre qué carta. El precio no: lo pone el catálogo al abrir el checkout, y el
webhook lo vuelve a validar contra la orden antes de otorgar nada.
"""

import logging

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from api import catalogo, mantenimiento, polar
from api.auth import AccountTokenAuthentication
from api.permissions import HasAccount
from api.models import Chart, PolarCheckout

logger = logging.getLogger(__name__)


class CheckoutView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def post(self, request):
        if mantenimiento.activo():
            # Cobrar y no poder entregar es la peor combinación posible: el
            # webhook acreditaría durante el deploy y el informe arrancaría
            # contra un contenedor que está por morir.
            return Response(
                {"error": "estamos actualizando el sitio, probá en unos minutos"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        codigo = request.data.get("producto")
        if not codigo:
            return Response(
                {"error": "falta el producto"}, status=status.HTTP_400_BAD_REQUEST
            )

        # La carta se resuelve contra la cuenta que pide: sin ese filtro se
        # compra un informe y se lo entrega en la carta de otro.
        carta = None
        chart_id = request.data.get("chart_id")
        if chart_id:
            carta = get_object_or_404(Chart, uuid=chart_id, account=request.user)

        # El idioma en el que está navegando. Decide dos cosas: a qué página lo
        # devuelve Polar después de pagar, y en qué idioma se escribe el
        # informe cuando el webhook lo arranque. Se valida contra la lista
        # blanca acá —no se concatena ni se guarda tal cual— porque viene del
        # navegador y termina en una URL y en la base.
        pedido = request.data.get("locale") or polar.LOCALE_POR_DEFECTO
        idioma = pedido if pedido in polar.LOCALES else polar.LOCALE_POR_DEFECTO

        try:
            checkout_id, url = polar.crear_checkout(
                request.user, codigo, chart=carta, locale=idioma,
            )
        except (KeyError, ValueError) as exc:
            # Producto que no está en el catálogo, o gratis. Es un pedido mal
            # armado, no una falla nuestra.
            logger.warning("checkout rechazado para %r: %s", codigo, exc)
            return Response({"error": "producto inválido"}, status=status.HTTP_400_BAD_REQUEST)
        except polar.PolarNoConfigurado:
            # Falta el token o la ficha en Polar: problema de configuración
            # nuestro, no de quien compra.
            logger.exception("checkout sin configurar para %r", codigo)
            return Response(
                {"error": "el cobro no está disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except polar.PolarError:
            logger.exception("polar no pudo abrir el checkout de %r", codigo)
            return Response(
                {"error": "no pudimos abrir el pago"}, status=status.HTTP_502_BAD_GATEWAY
            )

        # Después del éxito y no antes: una fila huérfana dejaría que el webhook
        # de otra orden resolviera contra ella.
        PolarCheckout.objects.create(
            checkout_id=checkout_id, account=request.user, codigo_producto=codigo,
            chart=carta, locale=idioma,
        )
        return Response({"url": url})


class CheckoutEstadoView(APIView):
    """En qué quedó una compra, y a dónde mandar a quien volvió de pagar.

    Lo consulta la página de retorno. Existe por una carrera que no se puede
    evitar: Polar redirige el navegador al instante y su webhook —el que
    acredita— puede llegar después. Sin esto la página tendría que adivinar, y
    adivinar mal es mostrarle el botón de comprar a alguien que acaba de pagar.

    Sólo responde sobre checkouts de quien pregunta: uno ajeno es 404, igual
    que una carta ajena.
    """

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, checkout_id: str):
        fila = get_object_or_404(PolarCheckout, checkout_id=checkout_id, account=request.user)

        if fila.acreditado_at is None:
            return Response({"estado": "pendiente"})

        # A la carta sólo si hay UNA cosa que ver ahí: el informe que ya arrancó
        # con el pago. Un pack son cinco informes para usar cuando la persona
        # quiera, así que el lugar donde eso se ve es su cuenta —aunque el pack
        # se haya comprado mirando una carta—.
        prod = catalogo.producto(fila.codigo_producto)
        suelto = len(prod.otorga) == 1 and prod.otorga[0][1] == 1
        # `chart` es SET_NULL: puede no estar cuando se pregunta, y mandar a
        # `/carta/None` sería un 404 en la cara de quien pagó.
        if suelto and fila.chart is not None:
            destino = {"tipo": "carta", "id": str(fila.chart.uuid)}
        else:
            destino = {"tipo": "cuenta"}
        return Response({"estado": "acreditado", "destino": destino})
