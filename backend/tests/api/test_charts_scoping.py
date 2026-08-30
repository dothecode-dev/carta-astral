import pytest
from rest_framework.test import APIClient
from api.auth import create_session
from api.models import Account, Interpretation
from interpret.prompts import PROMPT_VERSION


def _client(acc):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    return c


PAYLOAD = {"date": "1990-05-20", "time": "10:30", "lat": -34.6, "lng": -58.4}


@pytest.mark.django_db
def test_interpretation_scoped_to_account(monkeypatch, settings):
    """Account B cannot interpret account A's chart — must get 404 (multi-tenancy isolation)."""
    import api.interpretation_service as svc

    settings.INTERPRETATION_DAILY_CAP = 100
    # Prevent actual LLM call; if the scoping bug exists B would reach this and get 200.
    # (Antes mockeaba `build_interpretation`, del flujo viejo de interpretación
    # que la Task 0 retiró — la generación real corre en `completar_generacion`,
    # que arma el cliente con `_build_client`, no con ese nombre.)
    monkeypatch.setattr(svc, "_build_client", lambda: object())

    a = Account.objects.create()
    b = Account.objects.create()

    # A creates a chart (chart.account = a)
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert resp.status_code == 201
    a_uuid = resp.data["id"]

    # B tries to interpret A's chart — must be 404, not a cross-account read
    resp = _client(b).post(
        f"/api/charts/{a_uuid}/interpretation/",
        {"lang": "es", "tier": "largo"},
        format="json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_chart_visible_only_to_owner():
    a = Account.objects.create()
    b = Account.objects.create()
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert resp.status_code == 201
    uuid = resp.data["id"]
    assert _client(a).get(f"/api/charts/{uuid}/").status_code == 200
    assert _client(b).get(f"/api/charts/{uuid}/").status_code == 404


@pytest.mark.django_db
def test_chart_list_scoped_to_account():
    a = Account.objects.create()
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    resp = _client(a).get("/api/charts/")
    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    # otra cuenta no ve nada
    b = Account.objects.create()
    assert len(_client(b).get("/api/charts/").data["results"]) == 0
    # cross-exclusion: B creates its own chart; A still sees only 1, B sees only 1
    _client(b).post("/api/charts/", PAYLOAD, format="json")
    assert len(_client(a).get("/api/charts/").data["results"]) == 1
    assert len(_client(b).get("/api/charts/").data["results"]) == 1


@pytest.mark.django_db
def test_la_carta_expone_los_tiers_completos(client_autenticado, chart, account):
    """`interpretations` agrupa por idioma sólo los tiers COMPLETOS: una fila
    `completa=False` es la generación en curso que crea `iniciar_generacion`
    (Tarea 10), no una lectura disponible — anunciarla haría que la web
    ofrezca leer algo que todavía no existe.

    Usa `client_autenticado`/`chart` (comparten `account`), no `account_client`
    del brief: ese fixture crea su PROPIA cuenta, distinta de la dueña de
    `chart`, así que el GET siempre daba 404 sin importar los tiers —el test
    tal cual estaba escrito no podía pasar nunca, con o sin el fix.
    """
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="corto",
        text="x", completa=True, account=account,
    )
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="largo",
        text="", completa=False, account=account,      # en curso: no se anuncia
    )
    datos = client_autenticado.get(f"/api/charts/{chart.uuid}/").json()
    assert datos["interpretations"]["es"] == ["corto"]


@pytest.mark.django_db
def test_un_tier_completo_en_un_idioma_no_se_filtra_a_otro(client_autenticado, chart, account):
    """Un tier completo en "es" no debe aparecer bajo "en": si se armara la
    estructura con un solo set/list compartido entre idiomas en vez de un
    dict por idioma, este test lo detecta."""
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="corto",
        text="x", completa=True, account=account,
    )
    datos = client_autenticado.get(f"/api/charts/{chart.uuid}/").json()
    assert datos["interpretations"]["es"] == ["corto"]
    assert datos["interpretations"].get("en", []) == []


@pytest.mark.django_db
def test_listar_cartas_no_agrega_una_consulta_por_carta(client_autenticado, account):
    """El listado usa `prefetch_related("interpretations")` para no pagar una
    query por carta. Si `_chart_repr` arma `interpretations` con una consulta
    propia (en vez de iterar `chart.interpretations.all()`, que reusa el
    prefetch), el número de queries crece con la cantidad de cartas y el
    endpoint se degrada en silencio a medida que la cuenta acumula cartas."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from api.chart_service import create_chart

    def crear_cartas_con_interpretacion(n):
        for _ in range(n):
            c = create_chart(PAYLOAD, account=account)
            Interpretation.objects.create(
                chart=c, lang="es", prompt_version=PROMPT_VERSION, tier="corto",
                text="x", completa=True, account=account,
            )

    crear_cartas_con_interpretacion(2)
    with CaptureQueriesContext(connection) as pocas:
        client_autenticado.get("/api/charts/")

    crear_cartas_con_interpretacion(5)
    with CaptureQueriesContext(connection) as muchas:
        client_autenticado.get("/api/charts/")

    assert len(muchas.captured_queries) == len(pocas.captured_queries)
