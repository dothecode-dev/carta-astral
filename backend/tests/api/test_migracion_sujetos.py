"""Las migraciones del sujeto (0039 y 0047), probadas con los modelos
HISTÓRICOS. PLATA: un consumo sin sujeto es un informe que se podría cobrar dos
veces, y un consumo desvinculado con sujeto puesto es un informe regalado.

Con `MigrationExecutor` y no con el registro actual: desde la 0047
`Interpretation.sujeto` es obligatorio, así que el estado «nada tiene sujeto»
sólo existe en el esquema de antes."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def _migrar(destino: str):
    ex = MigrationExecutor(connection)
    ex.migrate([("api", destino)])
    return MigrationExecutor(connection).loader.project_state([("api", destino)]).apps


def _ultima() -> str:
    return MigrationExecutor(connection).loader.graph.leaf_nodes("api")[0][1]


@pytest.fixture
def en(request):
    """`en("0038_sujeto")`: la base en ese punto; al terminar, de vuelta a la última."""
    def _ir(destino):
        return _migrar(destino)
    yield _ir
    _migrar(_ultima())


def _cuenta(apps):
    return apps.get_model("api", "Account").objects.create()


def _carta(apps, cuenta):
    BirthData = apps.get_model("api", "BirthData")
    Chart = apps.get_model("api", "Chart")
    bd = BirthData.objects.create(date="1990-01-01", lat=0, lng=0, tz_name="UTC")
    return Chart.objects.create(account_id=cuenta.pk, birth_data=bd, data={}, engine_version="t")


def _modelos(apps):
    return (
        apps.get_model("api", "Sujeto"),
        apps.get_model("api", "Interpretation"),
        apps.get_model("api", "Movimiento"),
        apps.get_model("api", "PasarelaCheckout"),
    )


# --- 0039: cada carta con su sujeto natal, y cada fila con el de su carta ---


def test_la_0039_deja_cada_carta_y_cada_fila_con_su_sujeto(en):
    apps = en("0038_sujeto")
    _, Interpretation, Movimiento, PasarelaCheckout = _modelos(apps)
    cuenta = _cuenta(apps)
    c1, c2 = _carta(apps, cuenta), _carta(apps, cuenta)
    Interpretation.objects.create(chart=c1, lang="es", prompt_version="v", text="")
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=c2,
    )
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=cuenta, codigo_producto="informe_natal", chart=c2,
    )

    apps = _migrar("0039_rellenar_sujetos")
    Sujeto, Interpretation, Movimiento, PasarelaCheckout = _modelos(apps)

    assert Sujeto.objects.filter(producto="natal").count() == 2
    assert not Interpretation.objects.filter(sujeto__isnull=True).exists()
    assert Movimiento.objects.get(chart_id=c2.pk).sujeto.natal_de_id == c2.pk
    assert PasarelaCheckout.objects.get(checkout_id="cs_1").sujeto.natal_de_id == c2.pk


def test_la_0039_no_le_pone_sujeto_a_lo_que_no_tiene_carta(en):
    apps = en("0038_sujeto")
    _, _, Movimiento, PasarelaCheckout = _modelos(apps)
    cuenta = _cuenta(apps)
    otorgamiento = Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="otorgamiento",
        origen="compra", cantidad=1,
    )
    pack = PasarelaCheckout.objects.create(
        checkout_id="cs_p", account=cuenta, codigo_producto="pack_3_natal",
    )

    apps = _migrar("0039_rellenar_sujetos")
    _, _, Movimiento, PasarelaCheckout = _modelos(apps)

    assert Movimiento.objects.get(pk=otorgamiento.pk).sujeto_id is None
    assert PasarelaCheckout.objects.get(pk=pack.pk).sujeto_id is None


def test_rellenar_dos_veces_no_duplica_nada(en):
    """La 0047 vuelve a correr la función de la 0039."""
    from importlib import import_module

    rellenar = import_module("api.migrations.0039_rellenar_sujetos").rellenar
    apps = en("0038_sujeto")
    _, Interpretation, _, _ = _modelos(apps)
    c = _carta(apps, _cuenta(apps))
    Interpretation.objects.create(chart=c, lang="es", prompt_version="v", text="")

    apps = _migrar("0039_rellenar_sujetos")
    rellenar(apps)
    Sujeto, Interpretation, _, _ = _modelos(apps)

    assert Sujeto.objects.count() == 1
    assert Interpretation.objects.get().sujeto.natal_de_id == c.pk


def test_la_0039_respeta_un_sujeto_que_ya_estaba(en):
    apps = en("0038_sujeto")
    Sujeto = apps.get_model("api", "Sujeto")
    c = _carta(apps, _cuenta(apps))
    previo = Sujeto.objects.create(producto="natal", natal_de=c)

    apps = _migrar("0039_rellenar_sujetos")

    assert apps.get_model("api", "Sujeto").objects.get().pk == previo.pk


# --- 0047: re-rellenar lo que escribió el deploy 1, después restringir ---


def test_la_0047_rellena_lo_que_quedo_sin_sujeto(en):
    """Lo escrito en la ventana del deploy por un camino que no pasó por el
    `save()` del deploy 1 (un `update` o un `bulk_create`)."""
    apps = en("0046_entrada_cache")
    _, Interpretation, Movimiento, PasarelaCheckout = _modelos(apps)
    cuenta = _cuenta(apps)
    c = _carta(apps, cuenta)
    Interpretation.objects.bulk_create([Interpretation(chart=c, lang="es", prompt_version="v", text="")])
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=c,
    )
    PasarelaCheckout.objects.create(
        checkout_id="cs_v", account=cuenta, codigo_producto="informe_natal", chart=c,
    )

    apps = _migrar("0048_contraer_sujeto")
    Sujeto, Interpretation, Movimiento, PasarelaCheckout = _modelos(apps)
    s = Sujeto.objects.get(natal_de_id=c.pk)

    assert Interpretation.objects.get().sujeto_id == s.pk
    assert Movimiento.objects.get(chart_id=c.pk).sujeto_id == s.pk
    assert PasarelaCheckout.objects.get(checkout_id="cs_v").sujeto_id == s.pk


class _ConCarrera:
    """Los `apps` de la migración, pero listar las cartas corre antes `al_listar`:
    el contenedor viejo creando un sujeto entre la foto de `rellenar` y su
    `bulk_create`, que es lo que pasa en la ventana del deploy."""

    def __init__(self, apps, al_listar):
        self._apps, self._al_listar = apps, al_listar

    def get_model(self, app, nombre):
        modelo = self._apps.get_model(app, nombre)
        if nombre != "Chart":
            return modelo
        al_listar = self._al_listar

        class _Objetos:
            def values_list(self, *a, **k):
                al_listar()
                return modelo.objects.values_list(*a, **k)

        class _Carta:
            objects = _Objetos()

        return _Carta


def test_rellenar_tolera_un_sujeto_creado_por_el_contenedor_viejo_en_la_ventana(en):
    """La 0047 corre con el deploy 1 todavía atendiendo —y el webhook acredita
    aun con el cartel puesto—: si crea el sujeto de una carta después de la
    foto, el `bulk_create` choca con el único de `natal_de` y tira el deploy."""
    from importlib import import_module

    rellenar = import_module("api.migrations.0039_rellenar_sujetos").rellenar
    apps = en("0046_entrada_cache")
    Sujeto, Interpretation, _, _ = _modelos(apps)
    c = _carta(apps, _cuenta(apps))
    Interpretation.objects.bulk_create([Interpretation(chart=c, lang="es", prompt_version="v", text="")])

    rellenar(_ConCarrera(apps, lambda: Sujeto.objects.create(producto="natal", natal_de=c)))

    s = Sujeto.objects.get(natal_de_id=c.pk)
    assert Sujeto.objects.count() == 1
    assert Interpretation.objects.get().sujeto_id == s.pk


def test_la_0047_suelta_los_consumos_que_desvinculo_el_devolver_viejo(en):
    """El `devolver` anterior a la parte 2 desvinculaba sólo `chart`: un
    consumo natal sin carta y con sujeto se daría por cobrado y regalaría el
    informe junto con el derecho devuelto. Lo hacía `adoptar_huerfanas`."""
    apps = en("0046_entrada_cache")
    Sujeto, _, Movimiento, _ = _modelos(apps)
    cuenta = _cuenta(apps)
    s = Sujeto.objects.create(producto="natal", natal_de=_carta(apps, cuenta), account_id=cuenta.pk)
    desvinculado = Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=None, sujeto=s,
    )
    vigente = Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=s.natal_de, sujeto=s,
    )

    apps = _migrar("0048_contraer_sujeto")
    Movimiento = apps.get_model("api", "Movimiento")

    assert Movimiento.objects.get(pk=desvinculado.pk).sujeto_id is None
    assert Movimiento.objects.get(pk=vigente.pk).sujeto_id == s.pk


def test_tras_la_0047_el_sujeto_es_obligatorio_y_la_carta_no():
    from api.models import Interpretation

    assert Interpretation._meta.get_field("sujeto").null is False
    assert Interpretation._meta.get_field("chart").null is True
