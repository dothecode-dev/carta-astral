"""`GET /api/cupones/<codigo>/`: qué precio queda con ese cupón, para pintar.

Público como el catálogo: quien llega por un link con `?cupon=` tiene que ver
el precio tachado antes de crearse una cuenta. Y es SÓLO para pintar: la
validación que vale es la del checkout, que además sabe quién pide.

Devuelve el catálogo con la misma forma que `GET /api/catalogo/`, filtrado a
lo que el cupón abarca y con el precio final por producto. Nunca la
descripción interna, los usos que quedan ni los ids de Stripe: es la puerta
por la que se enumeraría el diccionario de códigos, y por eso lleva techo
por IP y responde lo mismo a «no existe» y a «está apagado».
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import cupones
from api.catalogo import CATALOGO
from api.models import Cupon


class CuponPublicoView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "cupon"

    def get(self, request, codigo: str):
        producto_pedido = request.query_params.get("producto")
        try:
            # Sin producto se valida contra el primero que abarca: alcanza para
            # saber si el cupón vive. Con producto, si aplica a ése.
            cupon = Cupon.objects.filter(codigo=Cupon.normalizar(codigo)).first()
            if cupon is None:
                raise cupones.CuponInvalido("inexistente")
            cupones.validar(codigo, producto_pedido or (cupon.productos[0] if cupon.productos else ""))
        except cupones.CuponInvalido as exc:
            return Response({"valido": False, "motivo": cupones.motivo_publico(exc.motivo)})

        productos = []
        for p in sorted(CATALOGO.values(), key=lambda p: p.precio_centavos):
            if p.codigo not in cupon.productos or p.precio_centavos <= 0:
                continue
            final, descuento = cupones.precio_final(p.precio_centavos, cupon.porcentaje)
            productos.append({
                "codigo": p.codigo,
                "precio_centavos": p.precio_centavos,
                "precio_final_centavos": final,
                "descuento_centavos": descuento,
                "moneda": "usd",
                "otorga": [{"codigo": c, "cantidad": n} for c, n in p.otorga],
            })
        return Response({
            "valido": True, "codigo": cupon.codigo, "porcentaje": cupon.porcentaje, "productos": productos,
        })
