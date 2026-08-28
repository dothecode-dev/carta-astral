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
