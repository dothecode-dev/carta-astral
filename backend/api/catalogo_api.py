"""`GET /api/catalogo/`: qué se vende y a cuánto.

Público: quien llega de una publicación tiene que poder ver los precios antes
de crearse una cuenta. Y es la única fuente del precio —la misma que valida el
webhook contra lo que Stripe cobró—, así que la web no puede anunciar un número
distinto del que se cobra.

Devuelve datos, no textos: los nombres y las descripciones viven en el i18n de
la web, traducidos a tres idiomas. Acá va lo que no se traduce.
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.catalogo import CATALOGO


class CatalogoView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        vendibles = [p for p in CATALOGO.values() if p.precio_centavos > 0]
        return Response({
            "productos": [
                {
                    "codigo": p.codigo,
                    "precio_centavos": p.precio_centavos,
                    # Fijo hoy, explícito igual: el día que haya otra moneda,
                    # la web no tiene que adivinar cuál está mostrando.
                    "moneda": "usd",
                    # Lo que hace la diferencia entre "US$ 125" y "US$ 125 por
                    # cinco informes".
                    "otorga": [
                        {"codigo": codigo, "cantidad": cantidad}
                        for codigo, cantidad in p.otorga
                    ],
                }
                for p in sorted(vendibles, key=lambda p: p.precio_centavos)
            ],
        })
