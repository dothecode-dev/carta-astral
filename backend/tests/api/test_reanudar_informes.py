"""Un informe pago que se cortó lo termina el cron, no el usuario.

`INTENTOS_MAXIMOS = 3` existía desde la Task 10, pero nadie gastaba el segundo
ni el tercero: el hilo de `views.py` hace UN intento y muere. Si una sección
falla, `completar_generacion` loguea, deja `intentos=1`, suelta el lock y
termina — y no hay cron, ni cola, ni reintento que la vuelva a llamar. La
política de reintentos estaba escrita y nunca se ejecutaba.

Pasó en producción el 01-09-2026: la interpretación 8 quedó con 2 de 8
secciones y `intentos=1`. La última sección se escribió 17:42:58 y el
contenedor siguió vivo hasta las 17:56 — no lo mató un deploy, se murió el
intento y nadie lo retomó.

Este comando es quien lo retoma. Corre periódicamente (tarea programada de
Coolify) y también a mano para rescatar lo que ya quedó tirado.
"""

import pytest
from django.core.management import call_command

from api import interpretation_service as svc
from api.models import Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION, SECCIONES

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpio():
    """El lock (`interp:lock:*`) vive en el cache, que es global al proceso de
    test y no se revierte por test como sí hace la base. Mismo patrón que
    `test_devolucion_informe.py`."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class _Stream:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        class R:
            content = [type("B", (), {"type": "text", "text": "una sección"})()]
            stop_reason = "end_turn"
            usage = type("U", (), {"output_tokens": 10})()

        return R()


class _FakeClient:
    """Cliente Anthropic falso, igual que el de `test_devolucion_informe.py`:
    responde texto fijo sin pegarle a la API real."""

    class _M:
        def stream(self, **kw):
            return _Stream()

    @property
    def messages(self):
        return _FakeClient._M()


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())


@pytest.fixture
def reanudados(monkeypatch):
    """Espía a quién ELIGE el comando, sin generar nada.

    La generación ya la cubren `test_devolucion_informe.py` y
    `test_informe_service.py`; lo único que este comando decide —y lo único
    que puede romper— es a cuáles filas les toca."""
    llamadas = []
    monkeypatch.setattr(
        svc, "completar_generacion",
        lambda interpretacion, chart, account: llamadas.append(interpretacion.pk),
    )
    return llamadas


def _a_medias(chart, account, *, intentos=1, secciones=2, prompt_version=PROMPT_VERSION):
    """Una interpretación como la que deja un intento que se cortó: pagada,
    con algunas secciones escritas, incompleta y sin lock tomado."""
    interp = Interpretation.objects.create(
        chart=chart, lang="es", tier="largo", prompt_version=prompt_version,
        account=account, completa=False, intentos=intentos,
    )
    for orden, seccion in enumerate(SECCIONES[:secciones]):
        InterpretationSection.objects.create(
            interpretation=interp, slug=seccion.slug, orden=orden,
            texto=f"texto de {seccion.slug}",
        )
    return interp


def test_reanuda_un_informe_caido_y_lo_termina(chart, account, fake_client):
    """El caso de producción, de punta a punta: 2 de 8 secciones, sin lock,
    con intentos disponibles."""
    interp = _a_medias(chart, account)

    call_command("reanudar_informes")

    interp.refresh_from_db()
    assert interp.completa is True
    assert interp.secciones.count() == len(SECCIONES)


def test_no_toca_un_informe_que_se_esta_escribiendo_ahora(chart, account, reanudados):
    """Con el lock vivo hay un hilo trabajando: meterse sería generar las
    mismas secciones dos veces, que es justo lo que el lock evita."""
    from django.core.cache import cache

    _a_medias(chart, account)
    cache.set(svc._lock_key(chart, "largo"), "un-token", timeout=600)

    call_command("reanudar_informes")

    assert reanudados == []


def test_no_toca_un_informe_que_agoto_los_intentos(chart, account, reanudados):
    """Agotados los tres, la política de RF21 ya decidió: se devuelve el
    derecho y se borra. Reintentar un cuarto sería gastarle plata al modelo
    sobre algo que ya se reembolsó."""
    _a_medias(chart, account, intentos=svc.INTENTOS_MAXIMOS)

    call_command("reanudar_informes")

    assert reanudados == []


def test_no_toca_un_informe_de_una_cuenta_borrada(chart, make_account, reanudados):
    """`Interpretation.account` es SET_NULL: borrada la cuenta, la fila queda
    con `account=None`. No hay a quién entregarle el informe ni a quién
    devolverle el derecho si falla, y `completar_generacion` necesita una
    cuenta para liquidar."""
    _a_medias(chart, None)

    call_command("reanudar_informes")

    assert reanudados == []


def test_no_toca_un_informe_de_una_version_de_prompt_vieja(chart, account, reanudados):
    """Mismo criterio que `interpretations` y `en_curso` en `_chart_repr`:
    sólo la versión vigente. Terminar un informe con el prompt viejo entrega
    algo que la web ni siquiera muestra."""
    _a_medias(chart, account, prompt_version="prompt-viejo")

    call_command("reanudar_informes")

    assert reanudados == []


def test_no_toca_un_informe_ya_terminado(chart, account, reanudados, interpretacion_completa):
    call_command("reanudar_informes")

    assert reanudados == []


def test_dice_cuantos_reanudo(chart, account, fake_client, capsys):
    """El comando lo dispara un cron: si no dice qué hizo, la única forma de
    saber si sirvió es consultar la base a mano."""
    _a_medias(chart, account)

    call_command("reanudar_informes")

    assert "terminados: 1" in capsys.readouterr().out


def test_un_informe_que_revienta_no_frena_a_los_demas(
    make_chart, account, monkeypatch, capsys,
):
    """El cron procesa una cola, no un caso. Si la primera fila revienta por
    algo que `completar_generacion` no contempla (la base se cae, un dato
    corrupto), las demás tienen que salir igual — si no, un informe roto
    bloquea a todos los que vengan detrás, indefinidamente, y nadie se
    entera."""
    primera = _a_medias(make_chart(account), account)
    segunda = _a_medias(make_chart(account), account)
    atendidas = []

    def _revienta_la_primera(interpretacion, chart, cuenta):
        if interpretacion.pk == primera.pk:
            raise RuntimeError("la base se cayó justo acá")
        atendidas.append(interpretacion.pk)

    monkeypatch.setattr(svc, "completar_generacion", _revienta_la_primera)

    call_command("reanudar_informes")

    assert atendidas == [segunda.pk]


def test_no_cuenta_como_terminado_un_informe_que_sigue_a_medias(
    chart, account, monkeypatch, capsys,
):
    """`completar_generacion` se traga las excepciones de la generación: vuelve
    sin error aunque el informe haya quedado igual de incompleto. Contar esas
    llamadas como éxito convierte la salida del cron en una mentira.

    Pasó de verdad el 02-09-2026: el comando informó "reanudados: 1 (fallidos:
    0)" sobre un informe que se acababa de cortar con `httpx.ReadTimeout`. La
    única razón por la que se supo fue el traceback, no el contador.
    """
    _a_medias(chart, account)
    monkeypatch.setattr(svc, "completar_generacion", lambda *a, **kw: None)

    call_command("reanudar_informes")

    assert "terminados: 0" in capsys.readouterr().out
