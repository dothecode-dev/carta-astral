import pytest
from django.core.cache import cache

from api import informe_service, interpretation_service
from api.models import Account, BirthData, Chart, Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

TOKEN = "tok-test"


@pytest.fixture(autouse=True)
def _sin_revision_del_trato(monkeypatch):
    """La revisión del trato (interpret/revision_trato.py) suma llamadas al
    mismo cliente falso, y estos tests cuentan llamadas para probar la
    mecánica de generación (secciones, cortes, reanudación). La revisión
    tiene sus propios tests (tests/interpret/test_revision_trato.py y
    tests/api/test_trato_informe.py); acá es la identidad."""
    monkeypatch.setattr(informe_service, "revisar_trato", lambda texto, trato, lang, client: texto)


@pytest.fixture(autouse=True)
def lock_tomado(chart):
    """Simula que ya se tomó el lock de esta carta con TOKEN, como hace
    `completar_generacion` antes de generar. Sin esto, el
    `renovar_lock` real (no mockeado) siempre devuelve False porque no hay
    ningún lock que renovar, y los tests de arriba abortarían en la primera
    sección por una razón ajena a lo que están probando."""
    # "largo" — el fixture `interpretacion` (que usan los tests de este
    # archivo salvo los que arman su propio tier vía `_interpretacion`,
    # abajo) crea su fila con el tier default del modelo, "largo".
    key = interpretation_service._lock_key(chart, "largo")
    cache.set(key, TOKEN, timeout=600)
    yield
    cache.delete(key)


class _Bloque:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Respuesta:
    def __init__(self, text="cuerpo de la sección", stop_reason="end_turn"):
        self.content = [_Bloque(text)]
        self.stop_reason = stop_reason


class _StreamCtx:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._resp


class ClienteFalso:
    """Fake del cliente Anthropic con la interfaz real de streaming
    (`messages.stream(...)` como context manager + `get_final_message()`),
    calcado del de `tests/interpret/test_generar_seccion.py`. `falla_en` hace
    que la llamada N-ésima levante RuntimeError, para simular un corte a
    mitad de informe."""

    def __init__(self, falla_en=None):
        self.falla_en = falla_en
        self.generadas = 0
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.generadas += 1
            self.outer.llamadas.append(kwargs)
            if self.outer.falla_en is not None and self.outer.generadas == self.outer.falla_en:
                raise RuntimeError("cayó la API")
            return _StreamCtx(_Respuesta())

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def test_genera_las_ocho_secciones_y_marca_completa(interpretacion):
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == 8
    assert interpretacion.completa is True


def test_si_falla_a_mitad_conserva_lo_escrito_y_no_marca_completa(interpretacion):
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == 4
    assert interpretacion.completa is False


def test_al_reanudar_no_vuelve_a_pedir_las_secciones_ya_escritas(interpretacion):
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)
    segundo = ClienteFalso()
    informe_service.generar_informe(interpretacion, segundo, TOKEN)
    # Cuatro ya estaban: sólo se piden las cuatro que faltan.
    assert segundo.generadas == 4
    interpretacion.refresh_from_db()
    assert interpretacion.completa is True


class _ChartFalso:
    """Un sujeto natal mínimo, sin base de datos: `secciones_aplicables` sólo
    lee `sujeto.natal_de.data.get("time_known", ...)`."""

    producto = "natal"

    def __init__(self, hora):
        self.natal_de = type("Carta", (), {"data": {"time_known": hora}})()


def _chart(hora):
    return _ChartFalso(hora)


def _interpretacion(tier):
    """Una `Interpretation` real (con cuenta y carta propias), del tier
    pedido. A diferencia del fixture `interpretacion` (siempre "largo"),
    esto permite probar la rama del tier corto sin tocar ese fixture."""
    account = Account.objects.create()
    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    chart = Chart.objects.create(birth_data=bd, data={}, engine_version="test", account=account)
    return Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account, tier=tier,
    )


def test_el_tier_corto_es_una_sola_seccion():
    """La lectura breve corre por la misma maquinaria que el informe completo
    (lock, persistencia por sección, reanudabilidad): lo único que cambia es
    cuántas secciones tiene el catálogo."""
    assert len(informe_service.secciones_aplicables(_chart(hora=True), "corto")) == 1


def test_el_tier_largo_sigue_teniendo_ocho():
    # El catálogo del informe completo no cambió con el agregado del tier:
    # sigue siendo el mismo que antes de esta tarea.
    assert len(informe_service.secciones_aplicables(_chart(hora=True), "largo")) == 8


def test_sin_hora_el_largo_pierde_las_de_casas_y_el_corto_no():
    # El filtro por hora de nacimiento sigue aplicando sólo al largo: la
    # lectura breve (`SECCION_BREVE`) no tiene `requiere_hora`, así que el
    # corto siempre da una sola sección, con o sin hora.
    sin_hora = _chart(hora=False)
    assert len(informe_service.secciones_aplicables(sin_hora, "largo")) == 7
    assert len(informe_service.secciones_aplicables(sin_hora, "corto")) == 1


def test_la_breve_usa_el_system_del_informe_entero(monkeypatch):
    """SYSTEM_PROMPTS_SECCION le dice al modelo que está escribiendo una parte
    de un informe mayor. Para la breve eso es mentira: produciría un texto que
    remite a secciones que nadie va a leer."""
    llamadas = []
    monkeypatch.setattr(
        informe_service, "build_interpretation",
        lambda *a, **k: llamadas.append("entero") or "texto breve",
    )
    monkeypatch.setattr(
        informe_service, "build_seccion",
        lambda *a, **k: llamadas.append("seccion") or "texto seccion",
    )
    interp = _interpretacion(tier="corto")
    informe_service.generar_informe(interp, client=object(), token="tok")
    assert llamadas == ["entero"]
    assert interp.secciones.count() == 1
    interp.refresh_from_db()
    assert interp.completa is True


def test_la_breve_pasa_una_sola_vez_por_el_juez(monkeypatch):
    veces = []
    monkeypatch.setattr(informe_service, "build_interpretation", lambda *a, **k: "breve")
    monkeypatch.setattr(informe_service, "revisar_trato", lambda t, *a, **k: veces.append(t) or t)
    interp = _interpretacion(tier="corto")
    informe_service.generar_informe(interp, client=object(), token="tok")
    assert veces == ["breve"]


def test_sin_hora_de_nacimiento_se_omite_la_seccion_de_casas(interpretacion):
    interpretacion.chart.data["time_known"] = False
    interpretacion.chart.save()
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    slugs = [s.slug for s in interpretacion.secciones.all()]
    assert "casas" not in slugs
    assert len(slugs) == 7


def test_el_texto_completo_se_arma_al_terminar(interpretacion):
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    interpretacion.refresh_from_db()
    # `text` se sigue llenando para no romper al PDF ni a la web mientras migran.
    assert "cuerpo de la sección" in interpretacion.text


def test_el_resumen_previo_crece_con_cada_seccion(interpretacion):
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="firma", orden=0, texto="Sol en Leo. " * 50,
    )
    previo = informe_service.resumen_previo(interpretacion)
    assert "Sol en Leo" in previo


def test_renueva_el_lock_despues_de_cada_seccion_persistida(interpretacion, monkeypatch):
    llamadas = []

    def _renovar(sujeto, tier, token):
        llamadas.append((sujeto.id, token))
        return True

    monkeypatch.setattr(informe_service, "renovar_lock", _renovar)
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    assert len(llamadas) == 8
    assert all(s_id == interpretacion.sujeto_id and token == TOKEN for s_id, token in llamadas)


def test_si_pierde_el_lock_justo_tras_la_ultima_seccion_igual_marca_completa(interpretacion, monkeypatch):
    """HALLAZGO 4 de code review: si `renovar_lock` devuelve False DESPUÉS de
    persistir la ÚLTIMA sección, ya no queda ningún trabajo pendiente —
    perder el lock ahí no puede dejar un informe entero (las ocho secciones
    ya escritas) marcado `completa=False` para siempre (404 en el GET,
    ausente del PDF). Sólo importa perder el lock cuando todavía hay
    secciones por pedir: ahí sí hay que abortar para no escribir en paralelo
    con el proceso que tomó el lock."""
    total = len(informe_service.secciones_aplicables(interpretacion.sujeto, interpretacion.tier))
    llamadas = []

    def _renovar(chart, tier, token):
        llamadas.append(1)
        return len(llamadas) < total  # falla justo en la renovación de la última

    monkeypatch.setattr(informe_service, "renovar_lock", _renovar)
    cliente = ClienteFalso()
    terminado = informe_service.generar_informe(interpretacion, cliente, TOKEN)
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == total
    assert interpretacion.completa is True
    assert cliente.generadas == total
    # Fix wave final: `True` es "terminó de intentar", no "está completo" —
    # acá coinciden, pero el contrato de retorno es el que necesita
    # `completar_generacion` para NO tratar esto como un aborto por lock
    # perdido (ver el contrapunto de abajo).
    assert terminado is True


def test_si_pierde_el_lock_aborta_sin_completar_ni_seguir_pidiendo(interpretacion, monkeypatch):
    cliente = ClienteFalso()

    monkeypatch.setattr(informe_service, "renovar_lock", lambda chart, tier, token: False)
    terminado = informe_service.generar_informe(interpretacion, cliente, TOKEN)
    interpretacion.refresh_from_db()
    # La sección que ya se había generado antes de perder el lock queda
    # persistida, pero no siguió pidiendo las demás ni marcó el informe
    # completo: perder el lock significa que otro proceso lo tomó y va a
    # terminar el informe por su cuenta.
    assert interpretacion.secciones.count() == 1
    assert interpretacion.completa is False
    assert cliente.generadas == 1
    # Fix wave final / Important: `False` es la señal que `completar_generacion`
    # necesita para NO contar este aborto limpio como un intento fallido —
    # sin ella, tres abortos por lock perdido devolvían el crédito y borraban
    # un informe que otro proceso seguía escribiendo de verdad.
    assert terminado is False


def test_nunca_llama_a_devolver_credito_ante_una_falla_parcial(interpretacion, monkeypatch):
    from api import canje

    def _explota(*args, **kwargs):
        raise AssertionError("generar_informe no debe llamar a canje.devolver")

    monkeypatch.setattr(canje, "devolver", _explota)
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)


def test_al_reanudar_el_contexto_previo_viaja_desde_la_base_no_desde_memoria(interpretacion):
    """Regresión del hallazgo de revisión: `resumen_previo` tiene que leer
    `interpretacion.secciones.all()` de la base en cada llamada, no acumular
    en memoria. Un proceso nuevo (el que reanuda) no tiene ningún acumulador:
    sólo tiene el pk. Por eso acá se recarga la interpretación con
    `Interpretation.objects.get(pk=...)`, simulando exactamente eso."""
    from api.models import Interpretation

    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="firma", orden=0,
        texto="MARCA-FIRMA-7b2c: el Sol domina esta carta.",
    )
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="mente", orden=1,
        texto="MARCA-MENTE-91af: Mercurio afila el detalle.",
    )
    recargada = Interpretation.objects.get(pk=interpretacion.pk)

    cliente = ClienteFalso()
    informe_service.generar_informe(recargada, cliente, TOKEN)

    enviado = cliente.llamadas[0]["messages"][0]["content"]
    assert "MARCA-FIRMA-7b2c" in enviado
    assert "MARCA-MENTE-91af" in enviado


def test_cada_seccion_recibe_su_parte_del_reparto(interpretacion):
    """Spec 2026-10-07 RF6: «mente» usa la oposición Luna–Mercurio que explica
    «tensiones» (viene después) y la síntesis no explica nada propio."""
    from tests.interpret.test_reparto import CARTA

    interpretacion.chart.data = CARTA
    interpretacion.chart.save()
    cliente = ClienteFalso()
    informe_service.generar_informe(interpretacion, cliente, TOKEN)
    pedidos = [ll["messages"][0]["content"] for ll in cliente.llamadas]
    assert "lo vas a ver en «Tensiones y aprendizajes»" in pedidos[1]
    assert "TE TOCA EXPLICAR" not in pedidos[-1]
    assert "como viste en «Tensiones y aprendizajes»" in pedidos[-1]


def test_sin_hora_el_reparto_no_inventa_casas_ni_cumulos(interpretacion):
    from tests.interpret.test_reparto import CARTA_SIN_HORA

    interpretacion.chart.data = CARTA_SIN_HORA
    interpretacion.chart.save()
    cliente = ClienteFalso()
    informe_service.generar_informe(interpretacion, cliente, TOKEN)
    pedidos = "\n".join(ll["messages"][0]["content"] for ll in cliente.llamadas)
    assert "cúmulo" not in pedidos
    # El foco de «trabajo» nombra el Medio Cielo; lo que no puede aparecer es
    # el MC como tema del reparto.
    assert "Medio Cielo: su signo" not in pedidos
    assert "Ascendente: su signo" not in pedidos


def _con_mail(interpretacion):
    interpretacion.account.email = "lectora@example.com"
    interpretacion.account.save()


def test_terminar_el_informe_manda_un_solo_mail_de_informe_listo(interpretacion, resend):
    """El cableado: `generar_informe` avisa al terminar (RF23)."""
    _con_mail(interpretacion)
    assert informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN) is True
    assert len(resend) == 1
    assert "listo" in str(resend[0]).lower()


def test_dos_pasadas_sobre_el_mismo_informe_mandan_un_solo_mail(interpretacion, resend):
    _con_mail(interpretacion)
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    informe_service.avisar_informe_listo(interpretacion)
    assert len(resend) == 1


def test_generar_informe_renueva_el_lock_del_sujeto_que_lo_tomo(interpretacion, monkeypatch):
    """RF23: el lock se toma por sujeto; renovarlo por carta daría False en un
    vínculo y el informe abortaría tras la primera sección. Con el lock REAL
    (lo toma `lock_tomado`): sólo se espía qué recibe."""
    from api.models import Sujeto

    vistos = []
    real = interpretation_service.renovar_lock
    monkeypatch.setattr(
        informe_service, "renovar_lock",
        lambda objetivo, tier, tok: vistos.append(objetivo) or real(objetivo, tier, tok),
    )
    assert informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    assert len(vistos) == 8
    assert all(isinstance(o, Sujeto) and o.pk == interpretacion.sujeto_id for o in vistos)
