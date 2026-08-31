"""Borra los dos contadores viejos de `Account`: `free_balance` y `paid_balance`.

La `0024` ya tradujo esos saldos a derechos nombrados por producto y todos los
consumidores de producción pasaron al canje. Lo que queda acá son dos columnas
que nadie lee ni escribe, y dejarlas es peor que borrarlas: invitan a que un
código futuro las vuelva a tocar y a que un lector crea que hay dos fuentes de
verdad sobre lo que una cuenta puede hacer.

Antes de dropear se verifica que no haya saldo PAGO huérfano — plata acreditada
contra `paid_balance` que nunca llegó a ser un `Derecho`. No es paranoia
gratuita: el webhook de pagos y `grant_credits` acreditaron ahí hasta dos
commits antes de esta migración, así que un despliegue parcial (la `0024`
aplicada, el código viejo todavía sirviendo) pudo dejar una compra sin derecho
equivalente. Si aparece una sola, la migración FALLA: es preferible un deploy
abortado a una columna borrada con plata adentro.

Qué cuenta como "ya traducido" y por lo tanto no es huérfano:

- El saldo positivo que la `0024` copió: dejó un `Movimiento` con
  `external_id="migracion:0024:<cuenta>:informe_natal"` y `cantidad` igual al
  `paid_balance` de ese momento. Si el saldo de hoy es ese mismo número, nada
  se movió después.
- El saldo negativo (clawback de un reembolso) que la `0024` convirtió en
  `Account.deuda`: se acepta si la deuda alcanza a cubrirlo.

Todo lo demás aborta. La guarda es deliberadamente conservadora: prefiere
frenar un deploy de más antes que dejar pasar plata sin derecho.
"""

from django.db import migrations

MOVIMIENTO_0024 = "migracion:0024:"


def verificar_sin_saldo_pago_huerfano(apps, schema_editor):
    Account = apps.get_model("api", "Account")
    Movimiento = apps.get_model("api", "Movimiento")

    traducido = dict(
        Movimiento.objects.filter(
            external_id__startswith=MOVIMIENTO_0024, codigo_producto="informe_natal",
        ).values_list("account_id", "cantidad")
    )

    huerfanos = []
    for cuenta in Account.objects.exclude(paid_balance=0).iterator():
        if traducido.get(cuenta.pk) == cuenta.paid_balance:
            continue  # la 0024 lo copió tal cual a un derecho de informe_natal
        if cuenta.paid_balance < 0 and cuenta.deuda == -cuenta.paid_balance:
            # El clawback ya vive en Account.deuda. La igualdad es EXACTA a
            # propósito: con `>=` se colaba plata del usuario. Una cuenta con
            # paid_balance=-5 cuando corrió la 0024 queda con deuda=5; si el
            # código viejo sigue sirviendo y esa cuenta COMPRA 3, el saldo
            # sube a -2 y la deuda sigue en 5. `5 >= 2` daba por traducido un
            # pago que nadie tradujo, y borrar la columna lo perdía. En el
            # deploy normal la 0024 deja `deuda == -paid_balance` exacto, así
            # que la igualdad no le quita tolerancia a ningún caso legítimo.
            continue
        huerfanos.append((cuenta.pk, cuenta.paid_balance))

    if huerfanos:
        detalle = ", ".join(f"cuenta {pk}: paid_balance={saldo}" for pk, saldo in huerfanos)
        raise RuntimeError(
            "0025 abortada: hay saldo pago sin derecho equivalente y borrar la columna "
            "lo perdería para siempre. Acreditá esos créditos con `canje.otorgar` "
            "(o `manage.py grant_credits`) y volvé a correr la migración. "
            f"Cuentas afectadas: {detalle}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0024_migrar_balances_a_derechos"),
    ]

    operations = [
        # La reversa es un noop: volver atrás re-crea las columnas vacías y es
        # `0024.revertir` quien sabe reconstruirlas desde los derechos.
        migrations.RunPython(
            verificar_sin_saldo_pago_huerfano, migrations.RunPython.noop, elidable=False,
        ),
        migrations.RemoveField(model_name="account", name="free_balance"),
        migrations.RemoveField(model_name="account", name="paid_balance"),
    ]
