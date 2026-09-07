"""`POST /api/checkout/`: abre una sesión de pago en Stripe.

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
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import analitica, catalogo, compra_service, cupones, mantenimiento, notificaciones, stripe_client
from api.auth import AccountTokenAuthentication
from api.permissions import HasAccount
from api.models import Chart, PasarelaCheckout

logger = logging.getLogger(__name__)


class CheckoutView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]
    # Con el cupón del 100 % este POST entrega un producto sin pasar por
    # Stripe: el techo es lo que lo separa de un bucle.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

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

        # El idioma en el que está navegando. Decide tres cosas: en qué idioma
        # ve el checkout de Stripe, a qué página vuelve después de pagar, y en
        # qué idioma se escribe el informe cuando el webhook lo arranque. Se valida contra la lista
        # blanca acá —no se concatena ni se guarda tal cual— porque viene del
        # navegador y termina en una URL y en la base.
        pedido = request.data.get("locale") or stripe_client.LOCALE_POR_DEFECTO
        idioma = (
            pedido if pedido in stripe_client.LOCALES else stripe_client.LOCALE_POR_DEFECTO
        )

        cupon = None
        codigo_cupon = request.data.get("cupon")
        if codigo_cupon:
            try:
                cupon = cupones.validar(codigo_cupon, codigo, account=request.user)
            except cupones.CuponInvalido as exc:
                logger.info("cupón %r rechazado para acc=%s: %s", codigo_cupon, request.user.pk, exc.motivo)
                return Response(
                    {"error": "el cupón no sirve", "motivo": cupones.motivo_publico(exc.motivo)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if cupon.porcentaje >= 100:
                return self._canjear_gratis(request, cupon, codigo, carta, idioma)

        try:
            checkout_id, url = stripe_client.crear_checkout(
                request.user, codigo, chart=carta, locale=idioma, cupon=cupon,
            )
        except (KeyError, ValueError) as exc:
            # Producto que no está en el catálogo, o gratis. Es un pedido mal
            # armado, no una falla nuestra.
            logger.warning("checkout rechazado para %r: %s", codigo, exc)
            return Response({"error": "producto inválido"}, status=status.HTTP_400_BAD_REQUEST)
        except stripe_client.StripeNoConfigurado:
            # Falta la clave o el precio en Stripe: problema de configuración
            # nuestro, no de quien compra.
            logger.exception("checkout sin configurar para %r", codigo)
            return Response(
                {"error": "el cobro no está disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except stripe_client.CuponRechazado:
            # Ya lo logueó `crear_checkout` con el código. Para quien compra es
            # «se agotó»: la alternativa —abrirle el pago a precio de lista—
            # sería cobrarle de más a alguien que creía tener descuento.
            return Response(
                {"error": "el cupón no sirve", "motivo": "agotado"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except stripe_client.StripeError:
            logger.exception("stripe no pudo abrir el checkout de %r", codigo)
            return Response(
                {"error": "no pudimos abrir el pago"}, status=status.HTTP_502_BAD_GATEWAY
            )

        # Después del éxito y no antes: una fila huérfana dejaría que el webhook
        # de otra orden resolviera contra ella. El descuento queda congelado
        # acá: es contra ESTO que el webhook valida lo que Stripe cobró.
        descuento = 0
        if cupon is not None:
            _, descuento = cupones.precio_final(catalogo.producto(codigo).precio_centavos, cupon.porcentaje)
        PasarelaCheckout.objects.create(
            checkout_id=checkout_id, account=request.user, codigo_producto=codigo,
            chart=carta, locale=idioma, cupon=cupon, descuento_centavos=descuento,
        )
        return Response({"url": url})

    def _canjear_gratis(self, request, cupon, codigo, carta, idioma):
        """El cupón del 100 % no pasa por Stripe: se resuelve acá, en la
        misma request, y la página de retorno lo encuentra ya acreditado.

        Es un POST que entrega un producto de US$ 29, así que lleva los
        frenos que un pago no necesita: una cuenta con deuda recibiría nada
        —`otorgar` cancela deuda antes de dar saldo— y una marcada por
        reembolsos repetidos es justo la que no debería recibir regalos.
        """
        cuenta = request.user
        if cuenta.deuda > 0 or cuenta.flagged:
            logger.warning("cupón %s: acc=%s con deuda o marcada, no se canjea", cupon.codigo, cuenta.pk)
            return Response(
                {"error": "esta cuenta no puede usar cupones", "motivo": "cuenta_no_habilitada"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            fila = cupones.canjear_gratis(cuenta, cupon, codigo, carta, idioma)
        except cupones.CuponInvalido as exc:
            # Perdió la carrera bajo el lock: otro se llevó el último lugar.
            return Response(
                {"error": "el cupón no sirve", "motivo": cupones.motivo_publico(exc.motivo)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Todo lo que hace `_acreditar` en el webhook después de la
        # transacción, y en el mismo orden. Fuera del átomo: hacen red.
        notificaciones.notificar(cuenta, "compra_acreditada", {"producto": codigo}, lang=idioma)
        analitica.evento(
            cuenta, "compra_completada",
            {"producto": codigo, "monto_centavos": 0, "locale": idioma, "cupon": cupon.codigo},
        )
        compra_service.arrancar_informe(cuenta, fila)
        return Response({"url": f"/{idioma}/compra?checkout_id={fila.checkout_id}"})


class CheckoutEstadoView(APIView):
    """En qué quedó una compra, y a dónde mandar a quien volvió de pagar.

    Lo consulta la página de retorno. Existe por una carrera que no se puede
    evitar: Stripe redirige el navegador al instante y su webhook —el que
    acredita— puede llegar después. Sin esto la página tendría que adivinar, y
    adivinar mal es mostrarle el botón de comprar a alguien que acaba de pagar.

    Sólo responde sobre checkouts de quien pregunta: uno ajeno es 404, igual
    que una carta ajena.
    """

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request, checkout_id: str):
        fila = get_object_or_404(PasarelaCheckout, checkout_id=checkout_id, account=request.user)

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
