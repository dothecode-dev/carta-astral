"""Las dos migraciones que cierran el modelo de cobro viejo. Superficie de PLATA.

- `0024_migrar_balances_a_derechos` traduce los dos contadores sueltos de
  `Account` a derechos nombrados por producto. Sin ella, desplegar el modelo
  de canje le devuelve 402 a TODAS las cuentas que ya existen: tienen saldo en
  los contadores y cero derechos, y `canje.puede()` sólo mira derechos.
- `0025_borrar_saldos_viejos` dropea esas dos columnas, con una guarda previa
  que aborta si encuentra saldo PAGO que nunca llegó a ser un derecho.

## Por qué estos tests montan un andamio y no usan `api.models` a secas

La versión anterior construía las filas con `Account(free_balance=…)` contra el
registro real de modelos. Eso dejó de compilar el día que la `0025` borró las
columnas: el modelo de hoy no las tiene y la tabla de test tampoco. Pero los
tests siguen valiendo —cubren plata que se movió una sola vez, contra datos
reales, sin posibilidad de re-correr— así que en vez de borrarlos se los apoya
en dos piezas:

1. `_apps_previas()` devuelve el estado de modelos que la migración VE cuando
   corre (el posterior a la `0023`), reconstruido desde el grafo de
   migraciones. Es el mismo `apps` que Django le pasa a un `RunPython`, así
   que `Account` ahí sí tiene los dos contadores.
2. `columnas_viejas` repone las dos columnas en la tabla de test con DDL
   directo, y el rollback de la transacción del test se las lleva. Sin esto el
   `SELECT` del modelo histórico pide columnas que ya no están en la base.

Ese andamio es la única forma de seguir ejerciendo estas dos migraciones sin
`django_test_migrations` (que no está en el repo). Las filas se crean con el
modelo histórico y no con INSERT a mano por lo mismo que en el resto del repo:
el ORM ya sabe armar la fila, y un INSERT escrito a mano se desincroniza con
el esquema en silencio.

Las consultas cruzadas usan `account_id=` y no `account=`: un modelo histórico
y uno real son dos clases distintas para el ORM aunque compartan tabla, y
`account=<instancia histórica>` levanta `ValueError`.
"""

import importlib
import logging

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

from api.models import Derecho, Movimiento, ProviderIdentity, SubTombstone

pytestmark = pytest.mark.django_db

_migracion = importlib.import_module("api.migrations.0024_migrar_balances_a_derechos")
_borrado = importlib.import_module("api.migrations.0025_borrar_saldos_viejos")


def _apps_previas():
    """El registro de modelos tal como lo ven la `0024` y la `0025`.

    `MigrationLoader(None)` no consulta la base (no le hace falta saber qué
    migraciones están aplicadas): sólo lee el grafo del disco.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return loader.project_state(("api", "0024_migrar_balances_a_derechos")).apps


@pytest.fixture
def columnas_viejas(db):
    """Repone `free_balance`/`paid_balance` en la tabla mientras dura el test.

    `DEFAULT 0` en las dos para que cualquier otro `INSERT` de la suite que
    caiga en el medio (una fixture que cree cuentas con el modelo de hoy, que
    no conoce estas columnas) no reviente contra el `NOT NULL`.

    No hay `DROP COLUMN` de vuelta y no hace falta: el DDL es transaccional en
    los dos motores que corre este repo (Postgres y SQLite), y el `db` de
    pytest-django envuelve cada test en una transacción que se rollbackea al
    terminar — las columnas se van con ella. Intentar dropearlas a mano ADEMÁS
    falla en Postgres: el `delete_account` de uno de estos tests deja triggers
    de FK diferidos pendientes y el motor rechaza el `ALTER TABLE` con
    "pending trigger events".
    """
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE api_account ADD COLUMN free_balance integer NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE api_account ADD COLUMN paid_balance integer NOT NULL DEFAULT 0")
    return _apps_previas().get_model("api", "Account")


def _migrar():
    _migracion.migrar(_apps_previas(), None)


def _revertir():
    _migracion.revertir(_apps_previas(), None)


def _verificar_borrado():
    _borrado.verificar_sin_saldo_pago_huerfano(_apps_previas(), None)


def _derecho(cuenta, codigo):
    return Derecho.objects.get(account_id=cuenta.pk, codigo_producto=codigo)


# --- 0024: los saldos se convierten en derechos ---


def test_el_saldo_gratis_y_el_pago_se_convierten_en_derechos(columnas_viejas):
    cuenta = columnas_viejas.objects.create(email="x@y.z", free_balance=2, paid_balance=1)

    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 2
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 1
    cuenta.refresh_from_db()
    assert cuenta.deuda == 0


def test_un_saldo_pago_negativo_se_convierte_en_deuda(columnas_viejas):
    """El saldo pago era signed: el clawback de un reembolso lo dejaba
    negativo. En el modelo nuevo eso no cabe en `cantidad_restante` (es
    Positive), y va a `Account.deuda`, que es donde el canje ya la busca."""
    cuenta = columnas_viejas.objects.create(email="d@y.z", free_balance=0, paid_balance=-2)

    _migrar()

    assert _derecho(cuenta, "informe_natal").cantidad_restante == 0
    cuenta.refresh_from_db()
    assert cuenta.deuda == 2


def test_deja_un_movimiento_de_ajuste_por_cada_derecho(columnas_viejas):
    cuenta = columnas_viejas.objects.create(email="m@y.z", free_balance=3, paid_balance=5)

    _migrar()

    movs = {m.codigo_producto: m for m in Movimiento.objects.filter(account_id=cuenta.pk)}
    assert set(movs) == {"lectura_breve", "informe_natal"}
    for codigo, mov in movs.items():
        assert mov.tipo == "otorgamiento"
        assert mov.origen == "ajuste"
        assert mov.external_id == f"migracion:0024:{cuenta.pk}:{codigo}"
    assert movs["lectura_breve"].cantidad == 3
    assert movs["informe_natal"].cantidad == 5


def test_es_idempotente(columnas_viejas):
    """El `external_id` es único GLOBAL: si la segunda corrida volviera a
    insertar el movimiento, esto reventaría con IntegrityError en vez de
    fallar en el assert."""
    cuenta = columnas_viejas.objects.create(email="i@y.z", free_balance=2, paid_balance=1)

    _migrar()
    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 2
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 1
    assert Movimiento.objects.filter(account_id=cuenta.pk).count() == 2


def test_no_pisa_un_derecho_que_ya_existia(columnas_viejas):
    """Una cuenta creada con el código nuevo (alta con `otorgar_bienvenida`)
    ya tiene su derecho antes de que corra la migración: sumarle otra vez el
    saldo gratis sería regalar el doble."""
    cuenta = columnas_viejas.objects.create(email="p@y.z", free_balance=3, paid_balance=0)
    Derecho.objects.create(
        account_id=cuenta.pk, codigo_producto="lectura_breve", cantidad_restante=3,
    )

    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 3
    assert Movimiento.objects.filter(
        account_id=cuenta.pk, codigo_producto="lectura_breve",
    ).count() == 0


def test_avisa_por_log_del_saldo_que_descarta(columnas_viejas, caplog):
    """El descarte tiene que dejar rastro: la migración corre UNA vez contra
    datos reales y no se puede re-correr para averiguar qué se perdió. En
    `informe_natal` el número descartado es plata."""
    cuenta = columnas_viejas.objects.create(email="log@y.z", free_balance=0, paid_balance=4)
    Derecho.objects.create(
        account_id=cuenta.pk, codigo_producto="informe_natal", cantidad_restante=1,
    )

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _migrar()

    assert [r.getMessage() for r in caplog.records] == [
        f"0024: la cuenta {cuenta.pk} ya tenía derecho de informe_natal; "
        f"se descarta el saldo viejo de 4",
    ]


def test_no_avisa_cuando_no_hay_saldo_que_descartar(columnas_viejas, caplog):
    """Contrapunto: el derecho de `lectura_breve` en cero de una cuenta ya
    migrada no descarta nada, y un warning por cada cuenta y cada producto
    ahogaría al que sí importa."""
    cuenta = columnas_viejas.objects.create(email="nolog@y.z", free_balance=0, paid_balance=0)
    Derecho.objects.create(
        account_id=cuenta.pk, codigo_producto="lectura_breve", cantidad_restante=0,
    )

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _migrar()

    assert caplog.records == []


def test_no_pisa_una_deuda_que_el_canje_ya_habia_anotado(columnas_viejas):
    """La guarda `if deuda and not cuenta.deuda`.

    Si la cuenta ya debe algo, esa deuda la anotó el código nuevo (`revocar`)
    y es la que sostiene el cobro de hoy: la del saldo pago negativo del
    ledger viejo se descarta. El desvío que eso acepta está anotado en la
    migración: la reversa devuelve `-1`, no el `-3` que sumaría las dos.
    """
    cuenta = columnas_viejas.objects.create(email="deu@y.z", free_balance=0, paid_balance=-2)
    columnas_viejas.objects.filter(pk=cuenta.pk).update(deuda=1)

    _migrar()

    cuenta.refresh_from_db()
    assert cuenta.deuda == 1
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 0

    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.paid_balance == -1  # desvío conocido y documentado, no un bug nuevo
    assert cuenta.deuda == 0


def test_la_reversa_reconstruye_los_saldos_desde_los_derechos(columnas_viejas):
    cuenta = columnas_viejas.objects.create(email="r@y.z", free_balance=2, paid_balance=4)

    _migrar()
    columnas_viejas.objects.filter(pk=cuenta.pk).update(free_balance=0, paid_balance=0)
    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.free_balance == 2
    assert cuenta.paid_balance == 4
    assert cuenta.deuda == 0


def test_la_reversa_devuelve_la_deuda_como_saldo_negativo(columnas_viejas):
    cuenta = columnas_viejas.objects.create(email="rd@y.z", free_balance=1, paid_balance=-3)

    _migrar()
    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.free_balance == 1
    assert cuenta.paid_balance == -3
    assert cuenta.deuda == 0


@override_settings(INSTALL_FREE_CREDITS=3)
def test_borrar_una_cuenta_migrada_deja_el_tombstone_correcto(columnas_viejas):
    """El puente entre la migración y el anti-abuso de `deletion.py`.

    Una cuenta migrada NO tiene movimientos de consumo: gastó 2 de sus 3
    lecturas gratis con el ledger viejo y la migración sólo ve el saldo que
    quedó (1). Si el tombstone se calculara contando movimientos de consumo,
    diría 0 y el usuario podría borrar la cuenta y volver a entrar para
    recibir otras 3 lecturas gratis.
    """
    from api.deletion import delete_account
    from api.identity import sub_hash
    from api.models import Account

    cuenta = columnas_viejas.objects.create(email="t@y.z", free_balance=1, paid_balance=0)
    ProviderIdentity.objects.create(provider="apple", sub="MIGRADA", account_id=cuenta.pk)

    _migrar()
    delete_account(Account.objects.get(pk=cuenta.pk))

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "MIGRADA"))
    assert tomb.free_credits_consumed == 2


# --- 0025: la guarda que impide borrar plata ---


def test_el_borrado_deja_pasar_el_saldo_que_la_0024_ya_tradujo(columnas_viejas):
    """El camino normal del deploy: la `0024` y la `0025` corren seguidas, sin
    nada que escriba en el medio. La guarda no puede frenar acá o el deploy
    del modelo de canje no sale nunca."""
    columnas_viejas.objects.create(email="ok@y.z", free_balance=3, paid_balance=7)

    _migrar()

    _verificar_borrado()  # no levanta


def test_el_borrado_deja_pasar_la_deuda_que_la_0024_anoto(columnas_viejas):
    """El saldo negativo no quedó en un derecho (no cabe: `cantidad_restante`
    es Positive) sino en `Account.deuda`. Eso también es "ya traducido"."""
    columnas_viejas.objects.create(email="neg@y.z", free_balance=0, paid_balance=-4)

    _migrar()

    _verificar_borrado()  # no levanta


def test_el_borrado_aborta_si_una_cuenta_endeudada_compro_despues_de_la_0024(columnas_viejas):
    """El agujero que dejaba comparar la deuda con `>=` en vez de con `==`.

    La cuenta debía 5 cuando corrió la `0024` (`paid_balance=-5` → `deuda=5`).
    El código viejo sigue sirviendo y la cuenta COMPRA 3: el saldo sube a `-2`
    y la deuda queda en 5, porque el canje nuevo todavía no la tocó. Con `>=`
    la guarda evaluaba `5 >= 2`, daba el saldo por traducido y borraba la
    columna: el usuario pagó 3 y no se le descontó nada de lo que debía.
    """
    cuenta = columnas_viejas.objects.create(email="deudor@y.z", free_balance=0, paid_balance=-5)

    _migrar()
    cuenta.refresh_from_db()
    assert cuenta.deuda == 5
    columnas_viejas.objects.filter(pk=cuenta.pk).update(paid_balance=-2)  # compró 3 por el camino viejo

    with pytest.raises(RuntimeError) as exc:
        _verificar_borrado()
    assert f"cuenta {cuenta.pk}: paid_balance=-2" in str(exc.value)


def test_el_borrado_aborta_si_entro_plata_despues_de_la_0024(columnas_viejas):
    """El caso que la guarda existe para atrapar: un despliegue parcial deja
    la `0024` aplicada y el código viejo sirviendo, así que el webhook
    acredita contra el contador y nadie crea el derecho. Borrar la columna
    ahí es perder una compra."""
    cuenta = columnas_viejas.objects.create(email="tarde@y.z", free_balance=0, paid_balance=2)

    _migrar()
    columnas_viejas.objects.filter(pk=cuenta.pk).update(paid_balance=12)  # +10 del webhook viejo

    with pytest.raises(RuntimeError) as exc:
        _verificar_borrado()
    assert f"cuenta {cuenta.pk}: paid_balance=12" in str(exc.value)


def test_el_borrado_aborta_con_una_cuenta_que_la_0024_nunca_vio(columnas_viejas):
    """Variante de lo mismo sin ningún movimiento de la `0024`: la cuenta se
    creó después de que la migración pasara y alguien le acreditó saldo pago
    por el camino viejo."""
    cuenta = columnas_viejas.objects.create(email="nueva@y.z", free_balance=0, paid_balance=5)

    with pytest.raises(RuntimeError) as exc:
        _verificar_borrado()
    assert f"cuenta {cuenta.pk}: paid_balance=5" in str(exc.value)


def test_el_borrado_deja_pasar_una_base_sin_saldo(columnas_viejas):
    columnas_viejas.objects.create(email="cero@y.z", free_balance=0, paid_balance=0)

    _verificar_borrado()  # no levanta
