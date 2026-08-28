import pytest
from django.db import IntegrityError

from api.models import InterpretationSection

pytestmark = pytest.mark.django_db


def test_una_seccion_cuelga_de_su_interpretacion(interpretacion):
    s = InterpretationSection.objects.create(
        interpretation=interpretacion, slug="firma", orden=0, texto="Tu Sol en Leo...",
    )
    assert s in interpretacion.secciones.all()


def test_no_se_puede_repetir_la_misma_seccion(interpretacion):
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="firma", orden=0, texto="a",
    )
    with pytest.raises(IntegrityError):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug="firma", orden=0, texto="b",
        )


def test_las_secciones_salen_en_orden(interpretacion):
    for i, slug in enumerate(["sintesis", "firma", "afectos"]):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=slug, orden={"firma": 0, "afectos": 2, "sintesis": 7}[slug], texto="x",
        )
    assert [s.slug for s in interpretacion.secciones.all()] == ["firma", "afectos", "sintesis"]


def test_una_interpretacion_nace_incompleta(interpretacion):
    assert interpretacion.completa is False
