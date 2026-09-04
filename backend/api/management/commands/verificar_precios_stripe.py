"""Compara los precios de Stripe con el catálogo, y arregla el impuesto.

Existe porque hasta el 04-09-2026 la única forma de saber cómo estaban los
precios de producción era escribir un script a mano y correrlo dentro del
contenedor. Ese día apareció lo que eso deja pasar: los tres precios live
tenían `tax_behavior: unspecified`, y cobraban bien sólo porque el default de
la cuenta era `inclusive`. Con el default en `exclusive` —que es el que trae
una cuenta nueva— el comprador europeo habría pagado el IVA por encima del
precio publicado, y ninguna alarma habría saltado: el webhook valida
`amount_subtotal`, que no cambia entre inclusive y exclusive.

No corre en el CI ni en los tests: necesita la clave live, que no está ni
puede estar en el repo. Es para correr a mano cuando se toquen los precios.

    python manage.py verificar_precios_stripe
    python manage.py verificar_precios_stripe --fijar-inclusive

`tax_behavior` es inmutable una vez que deja de ser `unspecified`, así que
`--fijar-inclusive` sólo puede actuar sobre los precios que todavía no lo
tienen puesto. Si un precio ya quedó en `exclusive`, no hay arreglo por API:
hay que crear otro precio y cambiar `STRIPE_PRECIOS`.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.catalogo import producto


class Command(BaseCommand):
    help = "Verifica los precios de Stripe contra el catálogo (y su tax_behavior)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fijar-inclusive",
            action="store_true",
            help="Pone tax_behavior=inclusive en los precios que estén en unspecified.",
        )

    def handle(self, *args, **options):
        import stripe

        if not settings.STRIPE_SECRET_KEY:
            raise CommandError("falta STRIPE_SECRET_KEY")
        if not settings.STRIPE_PRECIOS:
            raise CommandError("falta STRIPE_PRECIOS")

        stripe.api_key = settings.STRIPE_SECRET_KEY
        modo = "LIVE" if settings.STRIPE_SECRET_KEY.startswith("sk_live") else "test"
        self.stdout.write(f"modo: {modo}")

        try:
            ajustes = stripe.tax.Settings.retrieve()
            self.stdout.write(
                f"default de la cuenta: tax_behavior={ajustes.defaults.tax_behavior} "
                f"status={ajustes.status}"
            )
        except Exception as exc:  # la cuenta puede no tener Stripe Tax
            self.stdout.write(f"tax.Settings no disponible: {type(exc).__name__}: {exc}")

        problemas = 0
        for price_id, codigo in settings.STRIPE_PRECIOS.items():
            try:
                precio = stripe.Price.retrieve(price_id)
            except Exception as exc:
                self.stderr.write(f"{codigo}: {price_id} no se pudo leer: {exc}")
                problemas += 1
                continue

            try:
                esperado = producto(codigo).precio_centavos
            except KeyError:
                self.stderr.write(f"{codigo}: no está en el catálogo (mapeado a {price_id})")
                problemas += 1
                continue

            linea = (
                f"{codigo:16} {price_id} {precio.unit_amount / 100:>8.2f} "
                f"{precio.currency} tax_behavior={precio.tax_behavior} activo={precio.active}"
            )

            if precio.unit_amount != esperado:
                # Lo caro de verdad: la web publica el precio del catálogo y
                # Stripe cobra el suyo. Si difieren, se cobra un número que
                # nadie vio, y el webhook rechaza la acreditación porque valida
                # el subtotal contra el catálogo: pagó y no recibe.
                self.stderr.write(
                    f"{linea}  ✗ el catálogo dice {esperado / 100:.2f}"
                )
                problemas += 1
                continue

            if precio.tax_behavior == "unspecified" and options["fijar_inclusive"]:
                stripe.Price.modify(price_id, tax_behavior="inclusive")
                self.stdout.write(f"{linea}  → fijado en inclusive")
                continue

            if precio.tax_behavior != "inclusive":
                self.stderr.write(
                    f"{linea}  ✗ debería ser inclusive: el precio publicado lleva "
                    f"el impuesto adentro"
                )
                problemas += 1
                continue

            if not precio.active:
                self.stderr.write(f"{linea}  ✗ está inactivo: no se puede comprar")
                problemas += 1
                continue

            self.stdout.write(f"{linea}  ✓")

        faltan = {p.codigo for p in _codigos_vendibles()} - set(settings.STRIPE_PRECIOS.values())
        for codigo in sorted(faltan):
            self.stderr.write(f"{codigo}: está en el catálogo y no tiene precio en Stripe")
            problemas += 1

        if problemas:
            raise CommandError(f"{problemas} problema(s)")
        self.stdout.write(self.style.SUCCESS("los precios de Stripe coinciden con el catálogo"))


def _codigos_vendibles():
    """Los productos del catálogo que se cobran (los gratuitos no van a Stripe)."""
    from api.catalogo import CATALOGO

    return [p for p in CATALOGO.values() if p.precio_centavos > 0]
