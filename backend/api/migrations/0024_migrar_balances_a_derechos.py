"""Los dos contadores viejos pasan a derechos nombrados por producto.

`free_balance` y `paid_balance` eran dos números sueltos; el modelo de canje
pregunta por CAPACIDAD (`canje.puede`) y la capacidad sale de los `Derecho`.
Sin este paso, el deploy del modelo de canje le devuelve 402 a todas las
cuentas que ya existen: tienen saldo en los campos viejos y ni un derecho.
La rama no se puede desplegar por partes.

La traducción es la que ya usaban las dos superficies:

- `free_balance` -> derecho de `lectura_breve` (el tier corto, de regalo).
- `paid_balance` positivo -> derecho de `informe_natal` (el tier largo).
- `paid_balance` negativo -> `Account.deuda`. La columna vieja era signed
  porque el clawback de un reembolso podía dejarla bajo cero; en el modelo
  nuevo eso no cabe en `cantidad_restante` (es Positive) y vive en `deuda`,
  que es de donde `canje.otorgar` la descuenta en la próxima compra.

Cada derecho creado deja su `Movimiento` de `origen="ajuste"`: el invariante
del libro es que la cantidad de un derecho se reconstruya sumando sus
movimientos, y un derecho que aparece de la nada lo rompe. El `external_id`
es determinístico e incluye el producto porque el índice único de
`Movimiento.external_id` es GLOBAL, no por cuenta; también es lo que haría
fallar ruidosamente una segunda aplicación en vez de duplicar saldo en
silencio (no llega a pasar: el `get_or_create` de abajo corta antes).

Los códigos de producto están escritos acá y no importados de `api.catalogo`
a propósito: una migración congela el estado del código del día que se
escribió, y un catálogo que se edite mañana no puede cambiar retroactivamente
lo que esta migración hizo.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

FREE = "lectura_breve"
PAGO = "informe_natal"


def _traducir(Derecho, Movimiento, cuenta_id, codigo, cantidad) -> bool:
    """Crea el derecho y su movimiento. Devuelve False si el derecho ya estaba.

    Que ya esté significa que la cuenta se dio de alta con el código nuevo
    (`otorgar_bienvenida`) antes de que esta migración corriera: sumarle otra
    vez el `free_balance` sería regalar el doble.

    El descarte se loguea cuando hay saldo que descartar. Esto corre UNA sola
    vez contra datos reales y no se puede volver a correr para averiguar qué
    pasó: para `lectura_breve` descartar es lo correcto (el derecho ya tiene
    la verdad post-consumo), pero para `informe_natal` el número descartado es
    plata, y sin esta línea no queda registro de cuánta ni de quién.
    """
    _, creado = Derecho.objects.get_or_create(
        account_id=cuenta_id, codigo_producto=codigo,
        defaults={"cantidad_restante": cantidad},
    )
    if not creado:
        if cantidad > 0:
            logger.warning(
                "0024: la cuenta %s ya tenía derecho de %s; se descarta el saldo viejo de %s",
                cuenta_id, codigo, cantidad,
            )
        return False
    Movimiento.objects.create(
        account_id=cuenta_id, codigo_producto=codigo, tipo="otorgamiento",
        origen="ajuste", cantidad=cantidad,
        external_id=f"migracion:0024:{cuenta_id}:{codigo}",
        note="migración de saldos a derechos",
    )
    return True


def migrar(apps, schema_editor):
    Account = apps.get_model("api", "Account")
    Derecho = apps.get_model("api", "Derecho")
    Movimiento = apps.get_model("api", "Movimiento")

    for cuenta in Account.objects.all().iterator():
        pago = cuenta.paid_balance or 0
        _traducir(Derecho, Movimiento, cuenta.pk, FREE, cuenta.free_balance or 0)
        _traducir(Derecho, Movimiento, cuenta.pk, PAGO, max(pago, 0))

        deuda = max(-pago, 0)
        # `not cuenta.deuda` es la guarda: si la cuenta ya debe algo, esa
        # deuda la anotó el código nuevo y es la buena. Sin la guarda, una
        # segunda corrida —o una reversa seguida de una re-aplicación—
        # pisaría lo que el canje viene registrando.
        #
        # El desvío que esto acepta a sabiendas: una cuenta con las dos cosas
        # —`paid_balance` negativo del ledger viejo Y `deuda` del canje
        # nuevo— conserva la deuda nueva y DESCARTA la vieja; la reversa
        # devuelve entonces un `paid_balance` que no es el original (con
        # `paid_balance=-2` y `deuda=1` preexistente, vuelve `-1`, no `-3`).
        # Es intencional: preferimos perder una deuda vieja antes que pisar
        # la que el canje viene registrando, que es la que sostiene el cobro
        # de hoy. En producción el caso no existe (`deuda` se agregó en 0023,
        # con default 0, y nada la escribió todavía).
        if deuda and not cuenta.deuda:
            cuenta.deuda = deuda
            cuenta.save(update_fields=["deuda"])


def revertir(apps, schema_editor):
    """Reconstruye los contadores viejos desde los derechos.

    Volver a `0023` es volver a correr el código viejo, que sólo sabe leer
    `free_balance`/`paid_balance`: la reversa tiene que dejar esas dos
    columnas diciendo la verdad, incluida la plata que entró DESPUÉS de la
    migración (por eso se leen los derechos y no se guarda el valor previo).
    La deuda se re-encoda como saldo negativo, que es exactamente para lo que
    `paid_balance` era signed.

    No borra derechos ni movimientos: el código viejo los ignora, y borrarlos
    se llevaría puesto lo que el modelo nuevo haya registrado mientras estuvo
    vivo. Re-aplicar `migrar` después de esto es un no-op sobre los derechos
    que ya existen y vuelve a derivar la deuda del saldo negativo.
    """
    Account = apps.get_model("api", "Account")
    Derecho = apps.get_model("api", "Derecho")

    for cuenta in Account.objects.all().iterator():
        cantidades = dict(
            Derecho.objects
            .filter(account_id=cuenta.pk, codigo_producto__in=(FREE, PAGO))
            .values_list("codigo_producto", "cantidad_restante")
        )
        cuenta.free_balance = cantidades.get(FREE) or 0
        cuenta.paid_balance = (cantidades.get(PAGO) or 0) - cuenta.deuda
        cuenta.deuda = 0
        cuenta.save(update_fields=["free_balance", "paid_balance", "deuda"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0023_derecho_movimiento_deuda"),
    ]

    operations = [
        migrations.RunPython(migrar, revertir),
    ]
