"""`GET /api/compras/`: qué compró esta cuenta.

Lo mira la pantalla de cuenta. Muestra también lo que todavía no acreditó: si
alguien pagó y el webhook aún no llegó, esconder la compra haría pensar que se
perdió la plata.

Devuelve qué y cuándo, nada más. El `checkout_id` y el `payment_intent` son
para el soporte —sirven para buscar la operación en Stripe—, no para el
navegador.
"""

from rest_framework.response import Response
from rest_framework.views import APIView

from api.auth import AccountTokenAuthentication
from api.models import PasarelaCheckout
from api.permissions import HasAccount


class ComprasView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def get(self, request):
        # Filtrado por la cuenta que pregunta, igual que las cartas: las de
        # otro no existen.
        compras = PasarelaCheckout.objects.filter(account=request.user)
        return Response({
            "compras": [
                {
                    "codigo_producto": c.codigo_producto,
                    "acreditada": c.acreditado_at is not None,
                    "created_at": c.created_at,
                }
                # `Meta.ordering` ya las trae de la más nueva a la más vieja.
                for c in compras
            ],
        })
