"""`GET /api/compras/`: qué compró esta cuenta.

Lo mira la pantalla de cuenta. Muestra también lo que todavía no acreditó: si
alguien pagó y el webhook aún no llegó, esconder la compra haría pensar que se
perdió la plata.

Devuelve qué, cuándo, cuánto se pagó y con qué cupón, y cuánto volvió si
hubo reembolso. El `checkout_id` y el `payment_intent` son para el soporte
—sirven para buscar la operación en Stripe—, no para el navegador.

Un checkout abierto y nunca pagado deja de listarse a las 24 horas: es lo que
dura la sesión en Stripe, y después de eso no es un pago «procesándose», es
alguien que no compró. Sin este corte, un checkout abandonado decía
«Procesando el pago…» para siempre (visto en staging el 06-09-2026).
"""
import datetime as dt

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from api.auth import AccountTokenAuthentication
from api.catalogo import producto
from api.models import PasarelaCheckout
from api.permissions import HasAccount

VIDA_DE_UN_CHECKOUT = dt.timedelta(hours=24)


class ComprasView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request):
        # Filtrado por la cuenta que pregunta, igual que las cartas: las de
        # otro no existen.
        compras = PasarelaCheckout.objects.filter(account=request.user).filter(
            Q(acreditado_at__isnull=False) | Q(created_at__gte=timezone.now() - VIDA_DE_UN_CHECKOUT),
        ).select_related("cupon")
        return Response({
            "compras": [
                {
                    "codigo_producto": c.codigo_producto,
                    "acreditada": c.acreditado_at is not None,
                    "created_at": c.created_at,
                    "monto_centavos": _pagado(c),
                    "cupon": c.cupon.codigo if c.cupon is not None else None,
                    "reembolsado_centavos": c.reembolsado_centavos,
                }
                # `Meta.ordering` ya las trae de la más nueva a la más vieja.
                for c in compras
            ],
        })


def _pagado(c) -> int:
    """Lista menos el descuento congelado en la fila. Un producto que ya no
    está en el catálogo se muestra igual, con lo que se pueda decir de él."""
    try:
        return producto(c.codigo_producto).precio_centavos - c.descuento_centavos
    except KeyError:
        return 0
