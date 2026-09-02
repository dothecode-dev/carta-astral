import pytest

from api import informe_service
from api.models import InterpretationSection
from interpret.prompts import SECCIONES

pytestmark = pytest.mark.django_db


def _llenar(interpretacion):
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=s.slug, orden=i,
            texto="Primer párrafo de la sección.\n\n" + ("relleno " * 300),
        )


def test_muestra_las_ocho_secciones(interpretacion):
    _llenar(interpretacion)
    assert len(informe_service.resumen_gratis(interpretacion)) == 8


def test_de_cada_seccion_muestra_solo_el_primer_parrafo(interpretacion):
    _llenar(interpretacion)
    entrada = informe_service.resumen_gratis(interpretacion)[0]
    assert entrada["parrafo"] == "Primer párrafo de la sección."
    assert "relleno" not in entrada["parrafo"]


def test_dice_cuanto_falta_de_cada_seccion(interpretacion):
    _llenar(interpretacion)
    assert informe_service.resumen_gratis(interpretacion)[0]["restante"] > 100


def test_el_gratis_entero_es_corto(interpretacion):
    # No es la primera sección recortada: eso sería regalar Sol, Luna y
    # Ascendente, que es lo que más le importa a la gente.
    _llenar(interpretacion)
    total = sum(len(e["parrafo"].split()) for e in informe_service.resumen_gratis(interpretacion))
    assert total < 400


def test_el_indice_incluye_secciones_todavia_no_generadas(interpretacion):
    """La generación es reanudable y corre fuera del request (RF10): el
    resumen tiene que poder mostrarse con el informe a medio generar. El
    índice sale del catálogo (`SECCIONES`/`secciones_aplicables`), no de lo
    que ya está persistido — si saliera de `interpretacion.secciones.all()`,
    un informe con una sola sección lista mostraría un índice de una sola
    entrada en vez de las ocho prometidas."""
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0,
        texto="Primer párrafo.\n\n" + ("relleno " * 300),
    )
    salida = informe_service.resumen_gratis(interpretacion)
    assert len(salida) == 8
    assert [e["slug"] for e in salida] == [s.slug for s in SECCIONES]
    assert salida[0]["parrafo"] == "Primer párrafo."
    # Las siete restantes todavía no se generaron: se ve el título, no hay
    # texto que mostrar todavía.
    assert all(e["parrafo"] == "" for e in salida[1:])


def test_una_seccion_no_generada_no_suma_al_total_de_palabras(interpretacion):
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0,
        texto="Primer párrafo.\n\n" + ("relleno " * 300),
    )
    salida = informe_service.resumen_gratis(interpretacion)
    total = sum(len(e["parrafo"].split()) for e in salida)
    assert total == len("Primer párrafo.".split())


def test_titulos_en_el_idioma_de_la_interpretacion(interpretacion):
    interpretacion.lang = "en"
    interpretacion.save()
    salida = informe_service.resumen_gratis(interpretacion)
    assert salida[0]["titulo"] == SECCIONES[0].titulo["en"]


def test_sin_hora_de_nacimiento_el_indice_no_incluye_casas(interpretacion):
    interpretacion.chart.data["time_known"] = False
    interpretacion.chart.save()
    salida = informe_service.resumen_gratis(interpretacion)
    assert len(salida) == 7
    assert "casas" not in [e["slug"] for e in salida]


def _parrafo_realista(cantidad_palabras):
    """Un párrafo de apertura como el que realmente escribe el modelo: varias
    oraciones, sin relleno repetido, de la longitud que se le pida. Ni
    `SYSTEM_PROMPTS_SECCION` ni el pedido de cada sección le ponen un tope al
    párrafo de apertura — 80 a 120 palabras es perfectamente plausible para
    una narrativa cálida de 700 a 1000 palabras en total."""
    oracion = (
        "El Sol conversa con la Luna y traza un temperamento cálido y curioso, "
        "con una necesidad de reconocimiento que aparece en cada vínculo "
        "importante de tu vida, incluso en los que preferís no nombrar en voz alta. "
    )
    palabras = (oracion * (cantidad_palabras // len(oracion.split()) + 1)).split()
    return " ".join(palabras[:cantidad_palabras])


def test_con_parrafos_realistas_el_total_sigue_bajo_400(interpretacion):
    """Regresión: con `texto.partition('\\n\\n')` sin tope, un párrafo de
    apertura de 80-120 palabras (plausible para una sección de 700-1000)
    multiplicado por ocho secciones da 640-960 palabras — más del doble del
    límite de RF3, y ningún test con `"Primer párrafo de la sección."` (4
    palabras) lo hubiera visto nunca."""
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=s.slug, orden=i,
            texto=_parrafo_realista(100) + "\n\n" + ("relleno " * 300),
        )
    total = sum(len(e["parrafo"].split()) for e in informe_service.resumen_gratis(interpretacion))
    assert total < 400


def test_con_parrafos_realistas_sin_hora_el_total_sigue_bajo_400(interpretacion):
    interpretacion.chart.data["time_known"] = False
    interpretacion.chart.save()
    for i, s in enumerate(SECCIONES):
        if s.requiere_hora:
            continue
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=s.slug, orden=i,
            texto=_parrafo_realista(120) + "\n\n" + ("relleno " * 300),
        )
    salida = informe_service.resumen_gratis(interpretacion)
    assert len(salida) == 7
    total = sum(len(e["parrafo"].split()) for e in salida)
    assert total < 400


def test_el_corte_no_parte_una_palabra_ni_deja_puntuacion_colgando(interpretacion):
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0,
        texto=_parrafo_realista(100) + "\n\n" + ("relleno " * 300),
    )
    entrada = informe_service.resumen_gratis(interpretacion)[0]
    # Cortó: se nota con una elipsis, no termina de golpe.
    assert entrada["parrafo"].endswith("…")
    # Antes de la elipsis no queda un espacio ni un signo de puntuación
    # colgando (eso sería un corte prolijo a medias).
    antes_de_elipsis = entrada["parrafo"][: -len("…")]
    assert antes_de_elipsis[-1] not in " ,;:.!?¡¿-—"
    # Ninguna palabra del original quedó partida al medio: cada token del
    # párrafo mostrado (menos la elipsis) aparece completo en el original.
    original = _parrafo_realista(100).split()
    mostrado = antes_de_elipsis.split()
    assert mostrado == original[: len(mostrado)]


def test_una_seccion_corta_no_se_corta_ni_se_rellena(interpretacion):
    """Si el párrafo real es más corto que el tope, se muestra entero: sin
    elipsis y sin agregarle nada."""
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0,
        texto="Un párrafo corto de verdad.\n\n" + ("relleno " * 300),
    )
    entrada = informe_service.resumen_gratis(interpretacion)[0]
    assert entrada["parrafo"] == "Un párrafo corto de verdad."


def test_un_encabezado_no_es_el_arranque_de_la_seccion(interpretacion):
    """Pasó en producción el 01-09-2026: bajo "Tu firma" el teaser mostraba
    "## Tu firma" en crudo, y bajo "Cómo pensás y te comunicás", "# Cómo
    pensás y te comunicás".

    El modelo arranca algunas secciones repitiendo el título como encabezado
    markdown, y `partition("\\n\\n")` se lo llevaba tal cual. No es el arranque
    de la sección: es su título, que el teaser ya muestra aparte en
    `titulo` — y el componente que lo pinta (`ResumenCompleto`) lo hace como
    texto plano, así que la almohadilla se ve.
    """
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=s.slug, orden=i,
            texto=f"## {s.titulo['es']}\n\nEsto sí es el arranque.\n\n" + ("relleno " * 300),
        )

    entrada = informe_service.resumen_gratis(interpretacion)[0]

    assert entrada["parrafo"] == "Esto sí es el arranque."
