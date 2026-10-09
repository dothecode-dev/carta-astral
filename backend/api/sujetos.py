"""El sujeto de un informe pago (parte 2 de la spec de Vínculo).

Desde el deploy 2 (CONTRAER) el cobro y la generación reciben sólo sujetos; una
carta vale por su sujeto natal, que se obtiene con `sujeto_natal`.
"""

from django.db import IntegrityError, transaction

from api.models import Chart, Sujeto


def sujeto_natal(carta: Chart) -> Sujeto:
    """El sujeto natal de la carta; lo crea si no existe.

    Seguro ante carreras: la unicidad la pone `natal_de`, y quien pierde la
    carrera lee el que ganó en vez de crear un segundo."""
    existente = Sujeto.objects.filter(natal_de=carta).first()
    if existente is not None:
        return existente
    try:
        with transaction.atomic():
            return Sujeto.objects.create(
                producto=Sujeto.NATAL, natal_de=carta, account_id=carta.account_id,
            )
    except IntegrityError:
        return Sujeto.objects.get(natal_de=carta)


def a_sujeto(objetivo) -> Sujeto:
    """CONTRAER (deploy 2): el cobro recibe sujetos. Una carta acá es un
    llamador que se quedó en el deploy 1; un vínculo no tiene carta."""
    if not isinstance(objetivo, Sujeto):
        raise TypeError(f"se esperaba Sujeto, llegó {type(objetivo).__name__}")
    return objetivo
