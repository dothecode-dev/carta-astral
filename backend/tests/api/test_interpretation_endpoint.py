import datetime
import uuid

import pytest
from django.core.cache import cache

from api import interpretation_service as svc
from api.models import BirthData, Chart, Interpretation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _chart(account=None):
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"time_known": True}, engine_version="test", account=account)


class _Stream:
    def __init__(self, raises=None):
        self._raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._raises:
            raise self._raises

        class R:
            content = [type("B", (), {"type": "text", "text": "tu carta dice..."})()]
            stop_reason = "end_turn"

        return R()


class _FakeClient:
    class _M:
        def stream(self, **kw):
            return _Stream()

    @property
    def messages(self):
        return _FakeClient._M()


class _Boom:
    class _M:
        def stream(self, **kw):
            import anthropic

            return _Stream(raises=anthropic.AnthropicError("boom"))

    @property
    def messages(self):
        return _Boom._M()


@pytest.fixture
def fake_client(monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())


def test_post_returns_interpretation(account_client, fake_client):
    """Task 10: el POST deja de generar sincrónicamente (RF10) — devuelve 202
    y arranca el trabajo en un hilo aparte. Lo único verificable acá, en el
    hilo del request, es que ya existe la fila pendiente y que se cobró; el
    contenido generado y la devolución de crédito ante una falla se prueban
    en `tests/api/test_informe_endpoint.py`, sobre `interpretation_service`
    directamente (un hilo real no ve los datos de una transacción de test sin
    commitear, así que no hay forma confiable de probar la generación en sí
    a través de HTTP)."""
    c = _chart(account=account_client.account)
    antes = account_client.account.free_balance + account_client.account.paid_balance
    resp = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 202
    interp = Interpretation.objects.get(chart=c, lang="es", prompt_version=svc.PROMPT_VERSION)
    assert interp.completa is False
    account_client.account.refresh_from_db()
    assert account_client.account.free_balance + account_client.account.paid_balance == antes - 1


def test_default_lang_es(account_client, fake_client):
    c = _chart(account=account_client.account)
    resp = account_client.post(f"/api/charts/{c.uuid}/interpretation/", {"tier": "largo"}, format="json")
    assert resp.status_code == 202
    assert Interpretation.objects.get(chart=c).lang == "es"


def test_invalid_lang_400(account_client, fake_client):
    c = _chart(account=account_client.account)
    resp = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "fr", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 400
    assert "error" in resp.data


def test_missing_chart_404(account_client, fake_client):
    resp = account_client.post(
        f"/api/charts/{uuid.uuid4()}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 404


# `test_llm_error_503` (retirado en la Task 10): probaba que un fallo del
# modelo durante la generación respondiera 503 sincrónicamente. Con RF10 la
# generación corre en un hilo aparte, después de que la vista ya respondió —
# un fallo del LLM ya no puede volver sincrónico. El equivalente async (la
# generación muere y el crédito vuelve) está en
# `tests/api/test_informe_endpoint.py::test_si_la_generacion_muere_el_credito_vuelve`.


def test_lock_tomado_no_bloquea_el_202(account_client, fake_client, db_cache):
    """Con el lock de otra generación en curso tomado, la vista sigue
    aceptando el pedido (202): no hay body sincrónico que pueda confundirse
    con un error. El hilo de fondo, al no conseguir el lock, no duplica la
    generación (ver `completar_generacion`); es la contraparte async del
    409 que existía antes de la Task 10, cuando el POST todavía generaba en
    el request y un lock tomado era indistinguible de una falla del modelo.

    db_cache: el lock vive en DatabaseCache en producción, no en LocMem.
    """
    c = _chart(account=account_client.account)
    cache.add(svc._lock_key(c, "largo"), "otro-token", timeout=30)
    resp = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 202


def test_segundo_idioma_con_el_primero_en_curso_devuelve_409(account_client, fake_client):
    """BUG de la revisión de seguridad: pedir "es" y, con esa generación
    todavía en curso (`completa=False`), pedir "en" no puede aceptar un 202
    que cobre y nunca vaya a completarse. La vista responde 409 —el mismo
    código que ya espera la web (`web/app/api/charts/[id]/interpretation/
    route.ts`) para "generación en curso"— y no cobra nada."""
    c = _chart(account=account_client.account)
    antes = account_client.account.free_balance + account_client.account.paid_balance

    r1 = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert r1.status_code == 202

    r2 = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "en", "tier": "largo"}, format="json"
    )
    assert r2.status_code == 409

    account_client.account.refresh_from_db()
    assert account_client.account.free_balance + account_client.account.paid_balance == antes - 1


# `test_cap_reached_503` (retirado en la Task 6): probaba que el cap diario
# bloqueara este POST con un 503. El informe completo ("largo") se cobra
# siempre del lote paid, que bypassea el cap por diseño (RF9): pedirlo con
# INTERPRETATION_DAILY_CAP=0 no puede dar 503, va a dar 202 (con
# paid_balance, que `account_client` fondea) o 402 (sin él) pero nunca un cap
# alcanzado. Es exactamente lo que prueba
# `test_paid_generation_bypasses_cap_via_endpoint`, ahí abajo, que ya cubría
# este mismo escenario desde el lado "sí bypassea".
#
# Fix round 1, Important 4: retirar ese test dejó el `except CapReached:
# return 503` de la vista (`views.py`) sin ningún test en todo el repo —ni
# siquiera indirecto, porque el "largo" nunca toca el cap. La cobertura se
# repone mockeando `iniciar_generacion` para que lo levante directo: no
# prueba que el cap se alcance (eso es responsabilidad de
# `interpretation_service`, ya cubierto en sus propios tests), prueba que la
# vista traduce esa excepción a 503.


def test_cap_reached_503(account_client, monkeypatch):
    """El 503 de la vista es el mismo caso de siempre —`CapReached` cortando
    el POST antes de aceptar el 202— pero ya no se puede disparar con el cap
    real (ver el retiro de arriba): se fuerza directo, como hacen los tests
    de `QuotaExceeded`/`GenerationInProgress` para 402/409 en este mismo
    archivo."""
    from api.exceptions import CapReached

    def _levanta_cap(*a, **kw):
        raise CapReached()

    monkeypatch.setattr(svc, "iniciar_generacion", _levanta_cap)
    c = _chart(account=account_client.account)
    resp = account_client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 503


@pytest.mark.django_db(transaction=True)
def test_paid_generation_bypasses_cap_via_endpoint(make_account, monkeypatch, settings):
    """RF9 via HTTP: paid credit bypasses INTERPRETATION_DAILY_CAP=0 and returns 202."""
    from rest_framework.test import APIClient
    from api.auth import create_session

    settings.INTERPRETATION_DAILY_CAP = 0
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())

    acc = make_account(free_balance=0, paid_balance=1)
    token = create_session(acc)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    c = _chart(account=acc)
    resp = client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert resp.status_code == 202


def test_no_credits_returns_402(make_account, monkeypatch):
    """Zero available credits returns 402, no Interpretation is created, Claude is not called."""
    from rest_framework.test import APIClient
    from api.auth import create_session

    acc = make_account(free_balance=0, paid_balance=0)
    token = create_session(acc)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    client_built = []
    monkeypatch.setattr(svc, "_build_client", lambda: client_built.append(1) or _FakeClient())

    c = _chart(account=acc)
    resp = client.post(
        f"/api/charts/{c.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )

    assert resp.status_code == 402
    assert Interpretation.objects.count() == 0
    assert client_built == []  # _build_client (and thus Claude) was never called
