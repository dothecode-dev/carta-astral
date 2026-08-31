"""Borrado de cuenta: tombstone del free-tier consumido + borrado duro de
datos personales. El ledger (CreditTransaction) se conserva con account=NULL."""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from api import apple
from api.identity import sub_hash
from api.models import BirthData, Movimiento, SubTombstone

logger = logging.getLogger(__name__)

#: El producto del tier gratis. Escrito acá y no importado del catálogo por lo
#: mismo que en la migración 0024: si mañana el regalo de bienvenida cambia de
#: producto, esta cuenta ya consumió el de hoy.
PRODUCTO_GRATIS = "lectura_breve"


def free_consumidas(account) -> int:
    """Cuántas lecturas del tier gratis gastó esta identidad, para el tombstone.

    Es el número anti-abuso: `SubTombstone.free_credits_consumed` es lo que
    impide que borrar la cuenta y volver a entrar con el mismo sub regale
    otras `INSTALL_FREE_CREDITS` lecturas. Si sale de menos, se abre esa
    puerta; `_create_account` le resta este número al regalo.

    Se calcula sobre el libro de movimientos de `lectura_breve`, que es donde
    vive el gasto desde el modelo de canje. El contador suelto que se usaba
    antes ya no existe: lo borró la migración `0025`.

    La cuenta es `INSTALL_FREE_CREDITS - lo que le queda`, y lo que le queda
    es la suma firmada de TODOS sus movimientos de `lectura_breve`, no sólo
    los de consumo. Contar únicamente los consumos deja dos agujeros, los dos
    alcanzables desde el flujo público y los dos cubiertos por tests en
    `tests/api/test_account_delete.py`:

    - Una cuenta cuyo tombstone ya estaba agotado no recibe regalo, así que
      no tiene ni un movimiento: los consumos darían 0, el `update_or_create`
      bajaría el tombstone de 3 a 0 y el ciclo borrar → volver a entrar
      regalaría 3 lecturas cada vez, para siempre.
    - Una segunda vida con tombstone parcial (regalo de 1 sobre 3) que gasta
      esa lectura tiene 1 consumo, pero consumió 3 contando la vida anterior;
      el tombstone se PISA, no se acumula.

    La fórmula descansa en que `lectura_breve` NUNCA se vende: si un producto
    pago lo otorgara, las unidades compradas inflarían el restante y el
    tombstone quedaría por debajo de lo consumido — el lado que regala gratis.
    Esa premisa es un gate, no un supuesto:
    `tests/api/test_catalogo.py::test_ningun_producto_pago_otorga_lectura_breve`.

    La suma completa arrastra las dos cosas sola: el otorgamiento ya viene
    descontado por el tombstone anterior, y una devolución (generación que
    falló) vuelve a sumar, que es lo correcto — no se le cobra al usuario una
    lectura que no recibió. Para una cuenta migrada por la 0024 el único
    movimiento es el ajuste con el saldo que le quedaba, y la cuenta da lo
    mismo que daba el campo viejo.
    """
    restante = Movimiento.objects.filter(
        account=account, codigo_producto=PRODUCTO_GRATIS,
    ).aggregate(total=Sum("cantidad"))["total"] or 0
    return max(0, min(settings.INSTALL_FREE_CREDITS, settings.INSTALL_FREE_CREDITS - restante))


def delete_charts(account) -> None:
    """Borra todas las cartas de la cuenta y sus datos de nacimiento.

    Las interpretations cascadean con la carta. BirthData no cascadea solo
    (el FK va de Chart a BirthData), así que se barren los que quedan sin
    ninguna carta: contienen nombre, fecha y coordenadas de nacimiento.
    """
    with transaction.atomic():
        birth_ids = list(account.charts.values_list("birth_data_id", flat=True))
        account.charts.all().delete()
        BirthData.objects.filter(id__in=birth_ids, charts__isnull=True).delete()


def _revoke_apple(tokens) -> None:
    """Revoca en Apple los tokens de la cuenta ya borrada (guideline 5.1.1(v)).

    Best-effort a propósito: el borrado de datos ya ocurrió y no se deshace
    porque Apple esté caído. Lo que falla queda logueado como error.
    """
    if not tokens:
        return
    if not apple.is_configured():
        logger.error(
            "apple revoke omitido: faltan credenciales del server API (%d token/s pendientes)",
            len(tokens),
        )
        return
    for token in tokens:
        try:
            apple.revoke(token)
        except Exception as exc:  # AppleError / AppleNotConfigured
            logger.error("apple revoke falló para un token de cuenta borrada: %s", exc)


def delete_account(account) -> None:
    # Se leen ANTES del borrado; la llamada de red va DESPUÉS del commit, nunca
    # dentro del atomic (mantendría el lock de la fila durante el timeout de Apple).
    apple_tokens = list(
        account.identities.filter(provider="apple")
        .exclude(refresh_token="")
        .values_list("refresh_token", flat=True)
    )
    with transaction.atomic():
        consumed = free_consumidas(account)
        for ident in account.identities.all():
            SubTombstone.objects.update_or_create(
                sub_hash=sub_hash(ident.provider, ident.sub),
                defaults={"free_credits_consumed": consumed},
            )
        delete_charts(account)
        account.sessions.all().delete()
        account.devices.update(account=None)
        account.identities.all().delete()
        account.delete()  # CreditTransaction.account -> SET_NULL (ledger preservado)
    _revoke_apple(apple_tokens)
