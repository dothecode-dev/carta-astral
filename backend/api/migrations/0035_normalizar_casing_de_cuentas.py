"""Normaliza a minúsculas el `email` de las `Account` ya guardadas.

C3 (revisión de `puertas-de-acceso`): `_create_account` guardaba `vid.email`
tal cual llegaba del proveedor SSO, sin pasar por `normalizar()`. Google
manda el claim en minúsculas para gmail.com pero no para un dominio
Workspace, así que en producción pueden existir cuentas con casing mixto de
antes de este fix.

El fix de código (`resolve_account`) ya matchea sin distinguir mayúsculas
(`email__iexact`) y no depende de que esta migración corra para funcionar.
Igual se normaliza la columna acá, por dos razones: cualquier código futuro
que compare `Account.email` con `==` en vez de `iexact` no vuelve a pisar el
mismo pozo, y una cuenta con casing mixto es simplemente un dato sucio que no
tiene por qué quedar así.

Lo que esta migración NO hace: fusionar cuentas duplicadas. Si dos `Account`
ya existen con la misma dirección en casing distinto (el caso que
`resolve_account` ahora loguea con un warning cuando lo vuelve a ver),
normalizar el casing NO las une — `email` no es único en este modelo — y
unirlas de verdad implica decidir qué pasa con las cartas, derechos,
movimientos y `ProviderIdentity` de cada una, que es una decisión de negocio
y no algo que una migración de datos deba tomar sola. Esta migración deja
constancia en el log de qué direcciones quedaron así, para que se revisen a
mano.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def normalizar_casing(apps, schema_editor):
    Account = apps.get_model("api", "Account")

    vistos: dict[str, list[int]] = {}
    for cuenta in Account.objects.exclude(email="").iterator():
        normalizado = cuenta.email.strip().lower()
        vistos.setdefault(normalizado, []).append(cuenta.pk)
        if cuenta.email != normalizado:
            cuenta.email = normalizado
            cuenta.save(update_fields=["email"])

    for pks in vistos.values():
        if len(pks) > 1:
            logger.warning(
                "0035: %d cuentas comparten la misma dirección normalizada (pks=%s); "
                "revisar a mano, esta migración no las fusiona",
                len(pks), pks,
            )


def sin_reversa(apps, schema_editor):
    # No hay forma de reconstruir el casing original: no se guardó en ningún
    # lado antes de pisarlo. Revertir esta migración es un no-op a propósito
    # —el dato queda normalizado, que es un estado válido— en vez de fallar
    # la reversa por algo que no se puede deshacer.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0034_codigoacceso_envios"),
    ]

    operations = [
        migrations.RunPython(normalizar_casing, sin_reversa),
    ]
