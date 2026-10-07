"""RF5: el informe fija el trato al nacer y toda su generación lo usa.

Cambiar el trato de la carta después NO cambia un informe ya creado: ni sus
secciones pendientes (ni las que retoma el cron), ni sus traducciones.
"""

import pytest
from django.core.cache import cache
from django.core.management import call_command

from api import informe_service
from api import interpretation_service as svc
from api.models import Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION, SECCIONES

pytestmark = pytest.mark.django_db

TOKEN = "tok-test"


@pytest.fixture(autouse=True)
def _lock_vigente(monkeypatch):
    """Estos tests llaman a `traducir_informe` directo, sin el lock que toma
    `completar_generacion`: sin esto el `renovar_lock` real devuelve False y
    la traducción abortaría tras la primera sección por una razón ajena a lo
    que se prueba. Los tests de renovación lo pisan con su propio doble."""
    monkeypatch.setattr(informe_service, "renovar_lock", lambda chart, tier, token: True)


@pytest.fixture(autouse=True)
def _cache_limpio():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def llamadas(monkeypatch):
    """Falsea la generación y registra el `trato` que recibe cada llamada."""
    reg = {"seccion": [], "breve": [], "traduccion": []}

    def _seccion(chart_data, seccion, lang, previo, client, reparto="", trato=""):
        reg["seccion"].append(trato)
        return f"texto de {seccion.slug}"

    def _breve(chart_data, lang, prompt_version, client, trato=""):
        reg["breve"].append(trato)
        return "lectura breve"

    def _traduccion(text, target_lang, client, trato=""):
        reg["traduccion"].append(trato)
        return "traducido"

    monkeypatch.setattr(informe_service, "build_seccion", _seccion)
    monkeypatch.setattr(informe_service, "build_interpretation", _breve)
    monkeypatch.setattr(informe_service, "translate_interpretation", _traduccion)
    monkeypatch.setattr(svc, "_build_client", lambda: object())
    return reg


@pytest.fixture
def cuenta(make_account):
    return make_account(lecturas_breves=2, informes=2)


def _con_trato(make_chart, cuenta, trato):
    carta = make_chart(account=cuenta)
    carta.birth_data.trato = trato
    carta.birth_data.save(update_fields=["trato"])
    return carta


def _cambiar_trato(carta, trato):
    carta.birth_data.trato = trato
    carta.birth_data.save(update_fields=["trato"])


def test_el_informe_nace_con_el_trato_de_la_carta(make_chart, cuenta, llamadas):
    carta = _con_trato(make_chart, cuenta, "femenino")

    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="largo")

    assert interp.trato == "femenino"
    interp.refresh_from_db()
    assert interp.trato == "femenino"


def test_las_secciones_se_generan_con_el_trato_del_informe(make_chart, cuenta, llamadas):
    carta = _con_trato(make_chart, cuenta, "femenino")
    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="largo")

    svc.completar_generacion(interp, carta, cuenta)

    assert llamadas["seccion"] == ["femenino"] * len(SECCIONES)


def test_la_lectura_breve_se_genera_con_el_trato_del_informe(make_chart, cuenta, llamadas):
    carta = _con_trato(make_chart, cuenta, "masculino")
    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="corto")

    svc.completar_generacion(interp, carta, cuenta)

    assert llamadas["breve"] == ["masculino"]


def test_cambiar_la_carta_despues_no_cambia_las_secciones_pendientes(make_chart, cuenta, llamadas):
    carta = _con_trato(make_chart, cuenta, "femenino")
    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="largo")

    _cambiar_trato(carta, "masculino")
    svc.completar_generacion(interp, carta, cuenta)

    assert llamadas["seccion"] == ["femenino"] * len(SECCIONES)


def test_el_cron_retoma_con_el_trato_del_informe_no_el_de_la_carta(make_chart, cuenta, llamadas):
    """Review Focus 1: `reanudar_informes` llama a `completar_generacion`."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="largo")
    for orden, seccion in enumerate(SECCIONES[:2]):
        InterpretationSection.objects.create(
            interpretation=interp, slug=seccion.slug, orden=orden, texto="ya estaba",
        )
    interp.intentos = 1
    interp.save(update_fields=["intentos"])

    _cambiar_trato(carta, "masculino")
    call_command("reanudar_informes")

    interp.refresh_from_db()
    assert interp.completa is True
    assert llamadas["seccion"] == ["femenino"] * (len(SECCIONES) - 2)


def test_la_traduccion_nace_con_el_trato_del_origen(make_chart, cuenta, llamadas):
    """Review Focus 2."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    origen = Interpretation.objects.create(
        chart=carta, lang="es", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, completa=True, trato="femenino",
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=origen, slug=seccion.slug, orden=orden, texto="x",
        )

    _cambiar_trato(carta, "masculino")
    informe_service.traducir_informe(origen, "pt", object(), TOKEN)

    destino = Interpretation.objects.get(chart=carta, lang="pt", tier="largo")
    assert destino.trato == "femenino"
    assert llamadas["traduccion"] == ["femenino"] * len(SECCIONES)


def test_el_destino_ya_existente_con_otro_trato_se_alinea_con_el_origen(make_chart, cuenta, llamadas):
    """El camino del sibling: `iniciar_generacion` crea el destino con el
    trato ACTUAL de la carta, pero es una traducción del origen."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    origen = Interpretation.objects.create(
        chart=carta, lang="es", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, completa=True, trato="femenino",
    )
    InterpretationSection.objects.create(
        interpretation=origen, slug=SECCIONES[0].slug, orden=0, texto="x",
    )
    destino = Interpretation.objects.create(
        chart=carta, lang="pt", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, trato="masculino",
    )

    informe_service.traducir_informe(origen, "pt", object(), TOKEN)

    destino.refresh_from_db()
    assert destino.trato == "femenino"


def test_carta_sin_trato_usa_vacio(make_chart, cuenta, llamadas):
    carta = make_chart(account=cuenta)
    interp = svc.iniciar_generacion(carta, "es", cuenta, tier="largo")
    assert interp.trato == ""

    svc.completar_generacion(interp, carta, cuenta)

    assert llamadas["seccion"] == [""] * len(SECCIONES)


# --- Fix round 1: no mezclar secciones escritas de cero con traducidas ---


def _origen_completo(carta, cuenta, trato="femenino"):
    origen = Interpretation.objects.create(
        chart=carta, lang="es", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, completa=True, trato=trato,
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=origen, slug=seccion.slug, orden=orden, texto=f"es {seccion.slug}",
        )
    return origen


def test_un_destino_con_secciones_de_cero_se_retraduce_entero(make_chart, cuenta, llamadas):
    """Un "pt" empezó de cero, escribió 3 secciones y falló; después apareció el
    "es" completo. Terminarlo traduciendo sólo lo que falta mezclaba textos
    escritos de cero (otro trato, otro contenido) con traducciones."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    origen = _origen_completo(carta, cuenta, trato="femenino")
    destino = Interpretation.objects.create(
        chart=carta, lang="pt", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, trato="masculino",
    )
    for orden, seccion in enumerate(SECCIONES[:3]):
        InterpretationSection.objects.create(
            interpretation=destino, slug=seccion.slug, orden=orden, texto="escrita de cero",
        )

    informe_service.traducir_informe(origen, "pt", object(), TOKEN)

    destino.refresh_from_db()
    assert destino.trato == "femenino"
    assert destino.completa is True
    textos = {s.texto for s in destino.secciones.all()}
    assert textos == {"traducido"}
    assert destino.secciones.count() == len(SECCIONES)
    assert llamadas["traduccion"] == ["femenino"] * len(SECCIONES)


def test_reintento_de_una_traduccion_a_medias_no_retraduce_lo_hecho(make_chart, cuenta, monkeypatch, llamadas):
    carta = _con_trato(make_chart, cuenta, "femenino")
    origen = _origen_completo(carta, cuenta)

    def _falla_en_la_cuarta(text, target_lang, client, trato=""):
        if len(llamadas["traduccion"]) == 3:
            raise RuntimeError("cayó la API")
        llamadas["traduccion"].append(trato)
        return "traducido"

    monkeypatch.setattr(informe_service, "translate_interpretation", _falla_en_la_cuarta)
    with pytest.raises(RuntimeError):
        informe_service.traducir_informe(origen, "pt", object(), TOKEN)
    destino = Interpretation.objects.get(chart=carta, lang="pt", tier="largo")
    assert destino.secciones.count() == 3

    def _bien(text, target_lang, client, trato=""):
        llamadas["traduccion"].append(trato)
        return "traducido"

    monkeypatch.setattr(informe_service, "translate_interpretation", _bien)
    informe_service.traducir_informe(origen, "pt", object(), TOKEN)

    destino.refresh_from_db()
    assert destino.secciones.count() == len(SECCIONES)
    assert len(llamadas["traduccion"]) == len(SECCIONES)  # 3 + 5, ninguna repetida


def test_completar_generacion_retraduce_el_destino_escrito_de_cero(make_chart, cuenta, llamadas):
    """Por el camino real: el "pt" quedó a medias de cero y existe el "es"."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    pt = svc.iniciar_generacion(carta, "pt", cuenta, tier="largo")
    InterpretationSection.objects.create(
        interpretation=pt, slug=SECCIONES[0].slug, orden=0, texto="escrita de cero",
    )
    _origen_completo(carta, cuenta, trato="femenino")

    svc.completar_generacion(pt, carta, cuenta)

    pt.refresh_from_db()
    assert pt.completa is True
    assert {s.texto for s in pt.secciones.all()} == {"traducido"}


# --- Fix round 2: un informe ya entregado no se re-traduce por una foto vieja ---


def test_completar_generacion_con_foto_vieja_no_toca_un_informe_ya_entregado(make_chart, cuenta, llamadas):
    """El cron arma su lista con «pt» todavía `completa=False`; mientras tanto
    un hilo de usuario lo termina de cero y «es» se completa traduciéndose de
    él. Cuando el cron llega a su foto vieja de «pt», no puede tratarlo como
    pendiente: re-traducirlo desde «es» borraba las secciones de un informe
    ya entregado."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    pt = Interpretation.objects.create(
        chart=carta, lang="pt", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, completa=True, trato="femenino",
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=pt, slug=seccion.slug, orden=orden, texto=f"pt {seccion.slug}",
        )
    es = _origen_completo(carta, cuenta, trato="femenino")
    es.traducido_de = pt
    es.save(update_fields=["traducido_de"])
    antes = sorted(pt.secciones.values_list("id", "slug", "texto"))

    foto_vieja = Interpretation.objects.get(pk=pt.pk)
    foto_vieja.completa = False  # lo que el cron tenía en memoria

    svc.completar_generacion(foto_vieja, carta, cuenta)

    pt.refresh_from_db()
    assert pt.completa is True
    assert pt.traducido_de_id is None
    assert sorted(pt.secciones.values_list("id", "slug", "texto")) == antes
    assert llamadas == {"seccion": [], "breve": [], "traduccion": []}


def test_traducir_informe_no_toca_un_destino_ya_completo(make_chart, cuenta, llamadas):
    """Defensa propia de `traducir_informe`: un destino que en la base ya está
    completo no se descarta ni se re-traduce, aunque no sea traducción de
    este origen."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    origen = _origen_completo(carta, cuenta, trato="femenino")
    destino = Interpretation.objects.create(
        chart=carta, lang="pt", prompt_version=PROMPT_VERSION, tier="largo",
        account=cuenta, completa=True, trato="masculino", text="entregado",
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=destino, slug=seccion.slug, orden=orden, texto="escrita de cero",
        )
    antes = sorted(destino.secciones.values_list("id", "slug", "texto"))

    informe_service.traducir_informe(origen, "pt", object(), TOKEN)

    destino.refresh_from_db()
    assert destino.completa is True
    assert destino.traducido_de_id is None
    assert destino.trato == "masculino"
    assert destino.text == "entregado"
    assert sorted(destino.secciones.values_list("id", "slug", "texto")) == antes
    assert llamadas["traduccion"] == []


def test_perder_el_lock_al_traducir_no_gasta_un_intento(make_chart, cuenta, llamadas, monkeypatch):
    """Mismo contrato que la generación: abortar la traducción porque otro
    proceso tomó el lock no es un intento fallido."""
    carta = _con_trato(make_chart, cuenta, "femenino")
    _origen_completo(carta, cuenta, trato="femenino")
    pt = svc.iniciar_generacion(carta, "pt", cuenta, tier="largo")
    monkeypatch.setattr(informe_service, "renovar_lock", lambda chart, tier, token: False)

    svc.completar_generacion(pt, carta, cuenta)

    pt.refresh_from_db()
    assert pt.completa is False
    assert pt.intentos == 0
    assert len(llamadas["traduccion"]) == 1
