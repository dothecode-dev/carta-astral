import pytest
from django.core.cache import cache
from django.utils import timezone

from api import interpretation_service as svc
from api.interpretation_service import SinDerecho
from api.models import Account, BirthData, Chart, Interpretation

pytestmark = pytest.mark.django_db


def _account(lecturas_breves=None, informes=0):
    """Una cuenta fondeada con derechos. `lecturas_breves=None` usa
    `INSTALL_FREE_CREDITS`, que es lo que regala el alta real."""
    from django.conf import settings

    from tests.conftest import otorgar_derechos

    breves = settings.INSTALL_FREE_CREDITS if lecturas_breves is None else lecturas_breves
    acc = Account.objects.create()
    otorgar_derechos(acc, breves, informes)
    return acc


def _chart():
    bd = BirthData.objects.create(
        date="1989-07-14", time="23:45", time_known=True,
        lat=-34.5, lng=-58.4, tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"placements": []}, engine_version="test")


def test_quota_exceeded_blocks_new_generation(settings):
    settings.INSTALL_FREE_CREDITS = 0
    acc = _account()  # INSTALL_FREE_CREDITS=0 → sin derecho de lectura_breve
    with pytest.raises(SinDerecho):
        svc.iniciar_generacion(_chart(), "es", acc, tier="corto")


def test_cache_hit_served_with_zero_credits(settings):
    settings.INSTALL_FREE_CREDITS = 0
    acc = _account()  # INSTALL_FREE_CREDITS=0 → sin derechos
    chart = _chart()
    from interpret.prompts import PROMPT_VERSION
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="cached", account=acc,
        completa=True,  # una fila `completa=False` es "en curso", no una lectura servible
    )
    # 0 créditos pero ya existe: `iniciar_generacion` la encuentra
    # (`get_or_create` con `created=False`) y la devuelve sin volver a
    # consultar el ledger. tier="largo": el default del modelo, el mismo
    # tier de la fila creada arriba.
    out = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    assert out.text == "cached"


def test_paid_generation_bypasses_daily_cap(settings):
    """RF9: a paid generation bypasses the global daily cap and does not increment it.

    El cap se chequea (y, si corresponde, se incrementa) enteramente dentro
    de `iniciar_generacion` — no hace falta mockear el cliente del LLM ni
    completar la generación para probar esta garantía, a diferencia del
    flujo viejo (que armaba el texto entero en la misma llamada que cobraba)."""
    from api.canje import otorgar

    settings.INSTALL_FREE_CREDITS = 0
    settings.INTERPRETATION_DAILY_CAP = 0  # cap at its limit for free generations

    acc = Account.objects.create()
    otorgar(acc, "informe_natal", 1, origen="compra", external_id="test:paid-bypasses-cap")
    chart = _chart()

    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    cache.clear()

    before = cache.get(cap_key)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    after = cache.get(cap_key)

    assert isinstance(interp, Interpretation)
    assert before is None
    assert after is None  # paid generation never touches the cap counter


def test_la_breve_cobra_free_y_el_completo_cobra_paid(make_account):
    """RF9: el tier decide la capacidad, no al revés (Task 11). La breve
    ("corto") gasta el derecho de lectura_breve; el informe completo
    ("largo") gasta el de informe_natal — y son dos `Interpretation`
    distintas sobre la misma carta e idioma, no la misma fila cobrada dos
    veces."""
    from api.models import Derecho

    acc = make_account(lecturas_breves=1, informes=1)
    chart = _chart()
    svc.iniciar_generacion(chart, "es", acc, tier="corto")
    assert Derecho.objects.get(codigo_producto="lectura_breve").cantidad_restante == 0
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1
    svc.iniciar_generacion(chart, "es", acc, tier="largo")
    assert Derecho.objects.get(codigo_producto="lectura_breve").cantidad_restante == 0
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


def test_sin_free_la_breve_falla_diciendo_que_falto_free(make_account):
    """Sin derecho de lectura_breve, pedir la breve no cae al derecho de
    informe_natal aunque sobre ahí: `SinDerecho.capacidad` dice cuál faltó
    ("leer_breve"), para que la vista pueda mostrar la pantalla correcta
    ("te quedaste sin lecturas gratis", no "comprá el informe")."""
    acc = make_account(lecturas_breves=0, informes=5)
    with pytest.raises(SinDerecho) as exc:
        svc.iniciar_generacion(_chart(), "es", acc, tier="corto")
    assert exc.value.capacidad == "leer_breve"


def test_sin_paid_el_completo_falla_diciendo_que_falto_paid(make_account):
    """Contrapunto: sin derecho de informe_natal, pedir el informe completo
    no cae al derecho de lectura_breve aunque sobre ahí — `SinDerecho.
    capacidad` dice "leer_informe", no la otra capacidad."""
    acc = make_account(lecturas_breves=5, informes=0)
    with pytest.raises(SinDerecho) as exc:
        svc.iniciar_generacion(_chart(), "es", acc, tier="largo")
    assert exc.value.capacidad == "leer_informe"


def test_la_interpretacion_vacia_se_borra_si_no_hay_credito(make_account):
    """Sin esto queda una fila completa=False que hace que el próximo intento
    crea que hay una generación en curso y no arranque nunca."""
    acc = make_account(lecturas_breves=0, informes=0)
    chart = _chart()
    with pytest.raises(SinDerecho):
        svc.iniciar_generacion(chart, "es", acc, tier="corto")
    assert chart.interpretations.count() == 0
