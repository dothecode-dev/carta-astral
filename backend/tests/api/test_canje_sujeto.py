"""El canje, por sujeto. PLATA: la idempotencia («esta carta ya tiene su
informe canjeado») pasa de la carta al sujeto, y no puede perderse en el
camino: ni por llamar con la carta en un lugar y con el sujeto en otro, ni por
filas que el código viejo escribió sin sujeto durante el deploy.

Sobre una cuenta en blanco (`make_account()`), no sobre el fixture `account`,
que ya trae tres informes: cada test otorga exactamente lo que mide."""

import pytest

from api.canje import SinDerecho, aplicar_compra, canjear, devolver, otorgar
from api.catalogo import producto
from api.models import Derecho, Movimiento, Sujeto
from api.sujetos import sujeto_natal

pytestmark = pytest.mark.django_db


def _precio() -> int:
    # El precio NO es el real: `tests/api/conftest.py` fija uno de prueba (autouse).
    return producto("informe_natal").precio_centavos


@pytest.fixture
def cuenta(make_account):
    return make_account()


@pytest.fixture
def carta(make_chart, cuenta):
    return make_chart(account=cuenta)


def _restante(cuenta) -> int:
    return Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante


def _consumos(cuenta):
    return Movimiento.objects.filter(account=cuenta, tipo="consumo")


def test_canjear_deja_el_consumo_con_sujeto_y_carta(cuenta, carta):
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    canjear(cuenta, "leer_informe", carta)
    consumo = _consumos(cuenta).get()
    assert consumo.sujeto_id == sujeto_natal(carta).pk
    assert consumo.chart_id == carta.pk


def test_carta_y_su_sujeto_son_el_mismo_canje(cuenta, carta):
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:2")
    canjear(cuenta, "leer_informe", carta)
    canjear(cuenta, "leer_informe", sujeto_natal(carta))
    assert _consumos(cuenta).count() == 1
    assert _restante(cuenta) == 1


def test_un_consumo_huerfano_del_deploy_cuenta_como_ya_canjeado(cuenta, carta):
    """El código viejo escribió el consumo con carta y sin sujeto."""
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:3")
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        origen="compra", cantidad=-1, chart=carta,
    )
    canjear(cuenta, "leer_informe", sujeto_natal(carta))
    assert _consumos(cuenta).count() == 1
    assert _restante(cuenta) == 2


def test_un_sujeto_sin_carta_se_canjea_y_queda_sin_carta(cuenta):
    """Lo que será un vínculo: no tiene `natal_de`."""
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:4")
    s = Sujeto.objects.create(producto=Sujeto.VINCULO, account=cuenta)
    canjear(cuenta, "leer_informe", s)
    consumo = _consumos(cuenta).get()
    assert consumo.sujeto_id == s.pk
    assert consumo.chart_id is None


def test_dos_vinculos_distintos_se_cobran_por_separado(cuenta):
    """Ninguno de los dos tiene carta (`natal_de` vacío): si el «ya canjeado»
    mirara la carta y no el sujeto, el segundo figuraría como ya cobrado y la
    persona pagaría un informe que nunca se arranca."""
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:7")
    uno = Sujeto.objects.create(producto=Sujeto.VINCULO, account=cuenta)
    otro = Sujeto.objects.create(producto=Sujeto.VINCULO, account=cuenta)

    canjear(cuenta, "leer_informe", uno)
    canjear(cuenta, "leer_informe", otro)

    assert _consumos(cuenta).count() == 2
    assert _restante(cuenta) == 0


def test_dos_sujetos_distintos_son_dos_canjes(cuenta, carta):
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:5")
    canjear(cuenta, "leer_informe", carta)
    with pytest.raises(SinDerecho):
        canjear(cuenta, "leer_informe", Sujeto.objects.create(producto=Sujeto.VINCULO))


def test_devolver_por_sujeto_libera_el_canje(cuenta, carta):
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:6")
    s = sujeto_natal(carta)
    canjear(cuenta, "leer_informe", s)
    devolver(cuenta, "informe_natal", external_id="d:1", sujeto=s)

    assert _restante(cuenta) == 1
    consumo = _consumos(cuenta).get()
    assert consumo.sujeto_id is None and consumo.chart_id is None
    devolucion = Movimiento.objects.get(account=cuenta, tipo="devolucion")
    assert devolucion.sujeto_id == s.pk
    # Liberado: se puede volver a canjear.
    canjear(cuenta, "leer_informe", s)
    assert _restante(cuenta) == 0


def test_aplicar_compra_con_sujeto_canjea_ese_sujeto(cuenta):
    s = Sujeto.objects.create(producto=Sujeto.VINCULO, account=cuenta)
    aplicar_compra(cuenta, "informe_natal", _precio(), external_id="stripe:1", sujeto=s)
    assert _consumos(cuenta).get().sujeto_id == s.pk
    assert _restante(cuenta) == 0


def test_aplicar_compra_sin_carta_ni_sujeto_acredita_y_no_canjea(cuenta):
    """La carta se borró entre el checkout y el webhook: hoy se acredita igual."""
    aplicar_compra(cuenta, "informe_natal", _precio(), external_id="stripe:2")
    assert _restante(cuenta) == 1
    assert not _consumos(cuenta).exists()


def test_una_devolucion_del_codigo_viejo_permite_volver_a_cobrar(cuenta, carta):
    """El `devolver` viejo (durante el deploy) repone el derecho y desvincula el
    consumo sólo por carta. El informe se tiene que poder volver a cobrar: si
    no, sería un informe gratis más el derecho devuelto."""
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:8")
    canjear(cuenta, "leer_informe", carta)
    # Lo que hace el código viejo al devolver:
    _consumos(cuenta).update(chart=None)
    Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").update(
        cantidad_restante=1,
    )

    canjear(cuenta, "leer_informe", carta)

    assert _restante(cuenta) == 0
    assert _consumos(cuenta).filter(sujeto__isnull=False).count() == 1
