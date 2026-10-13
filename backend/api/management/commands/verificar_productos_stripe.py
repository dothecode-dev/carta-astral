"""Compara `STRIPE_PRODUCTOS` con los Products de Stripe.

Reemplaza a `verificar_precios_stripe` (13-10-2026): el precio ya no vive en
Stripe —va en cada sesión, `price_data`—, así que lo que puede estar mal es
el Product: que exista, esté activo, tenga un `tax_code` (Managed Payments
lo exige para ser elegible) y que su `metadata.codigo_producto` sea el
nuestro. No corre en CI: necesita la clave.

    python manage.py verificar_productos_stripe
"""

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.catalogo import a_la_venta


class Command(BaseCommand):
    help = "Verifica los Products de Stripe contra STRIPE_PRODUCTOS y el catálogo."

    def handle(self, *args, **options):
        if not settings.STRIPE_SECRET_KEY:
            raise CommandError("falta STRIPE_SECRET_KEY")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        modo = "LIVE" if settings.STRIPE_SECRET_KEY.startswith("sk_live") else "test"
        self.stdout.write(f"modo: {modo}")
        problemas = []
        for codigo, product_id in settings.STRIPE_PRODUCTOS.items():
            try:
                prod = stripe.Product.retrieve(product_id)
            except stripe.StripeError as exc:
                problemas.append(f"{codigo}: {product_id} no se pudo leer ({type(exc).__name__})")
                continue
            if not prod.active:
                problemas.append(f"{codigo}: {product_id} está inactivo")
            if not prod.tax_code:
                problemas.append(f"{codigo}: {product_id} sin tax_code (Managed Payments lo exige)")
            declarado = (prod.metadata or {}).get("codigo_producto")
            if declarado != codigo:
                problemas.append(f"{codigo}: {product_id} dice metadata.codigo_producto={declarado!r}")
            self.stdout.write(f"{codigo} → {product_id} activo={prod.active} tax_code={prod.tax_code}")
        for p in a_la_venta():
            if p.codigo not in settings.STRIPE_PRODUCTOS:
                problemas.append(f"{p.codigo} está a la venta y no tiene Product")
        if problemas:
            raise CommandError("\n".join(problemas))
        self.stdout.write(self.style.SUCCESS("todo alineado"))
