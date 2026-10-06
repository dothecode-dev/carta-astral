"""El sujeto de un informe pago, y el puente con la carta mientras convivan.

Parte 2 de la spec de Vínculo. En el deploy 1 (EXPANDIR) las funciones de
cobro y generación aceptan una carta o un sujeto, y `a_sujeto` lo resuelve: así
la idempotencia del cobro y los locks ya son por sujeto sin que cambie ningún
llamador. En el deploy 2 (CONTRAER) sólo aceptan sujetos, y
`adoptar_huerfanas` desaparece.
"""

from django.db import IntegrityError, transaction

from api.models import Chart, Interpretation, Movimiento, PasarelaCheckout, Sujeto


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


def adoptar_huerfanas(sujeto: Sujeto) -> None:
    """Le asigna el sujeto a las filas de su carta que se escribieron sin él.

    Existen por el deploy: `entrypoint.sh` migra en el contenedor nuevo
    mientras el viejo sigue atendiendo, y el webhook de Stripe acredita
    incluso con el cartel de mantenimiento puesto. Lo que el código viejo
    escribe en esa ventana llega sin sujeto; sin adoptarlo, el informe de una
    compra hecha durante el deploy no figuraría como «ya canjeado» y se podría
    cobrar dos veces. El deploy 2 rellena todo y borra esta función."""
    if sujeto.natal_de_id is None:
        return
    carta_id = sujeto.natal_de_id
    Interpretation.objects.filter(chart_id=carta_id, sujeto__isnull=True).update(sujeto=sujeto)
    Movimiento.objects.filter(chart_id=carta_id, sujeto__isnull=True).update(sujeto=sujeto)
    PasarelaCheckout.objects.filter(chart_id=carta_id, sujeto__isnull=True).update(sujeto=sujeto)
    # Y al revés: el `devolver` viejo desvincula sólo con `update(chart=None)` y
    # deja el sujeto puesto. Un consumo natal sin carta es eso —el código nuevo
    # siempre lo escribe con `chart`, y si la carta se borra el sujeto natal cae
    # con ella—: sin soltarlo, el canje lo daría por cobrado y regalaría el
    # informe junto con el derecho devuelto.
    Movimiento.objects.filter(sujeto=sujeto, tipo="consumo", chart__isnull=True).update(sujeto=None)


def a_sujeto(objetivo, adoptar: bool = True) -> Sujeto:
    """Carta o sujeto → sujeto. Con `adoptar`, también trae las huérfanas.

    `adoptar=False` es para los locks: se consultan una vez por sección del
    informe y no necesitan las filas, sólo la clave."""
    if isinstance(objetivo, Sujeto):
        sujeto = objetivo
    elif isinstance(objetivo, Chart):
        sujeto = sujeto_natal(objetivo)
    else:
        raise TypeError(f"se esperaba Chart o Sujeto, llegó {type(objetivo).__name__}")
    if adoptar:
        adoptar_huerfanas(sujeto)
    return sujeto
