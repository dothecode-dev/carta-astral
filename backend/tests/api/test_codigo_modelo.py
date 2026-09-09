import pytest
from django.utils import timezone

from api.models import Account, CodigoAcceso, ProviderIdentity

pytestmark = pytest.mark.django_db


def test_el_mail_es_un_proveedor_de_identidad_valido():
    cuenta = Account.objects.create(email="juan@gmail.com", email_verified=True)
    identidad = ProviderIdentity.objects.create(
        provider="email", sub="juan@gmail.com", account=cuenta,
    )
    identidad.full_clean()  # falla si "email" no está en PROVIDERS


def test_una_direccion_puede_tener_varios_codigos_vigentes():
    """Hallazgo I1 de la revisión final: la UniqueConstraint parcial que
    bloqueaba un segundo código vigente por dirección se sacó a propósito —
    era lo que hacía que pedir un código nuevo invalidara el que la persona
    estaba tipeando. Ahora conviven varias filas vigentes para la misma
    dirección sin pisarse; no hace falta Postgres para esto, no queda ninguna
    constraint que lo impida en ningún motor."""
    ahora = timezone.now()
    CodigoAcceso.objects.create(
        email="juan@gmail.com", codigo_hash="a" * 64,
        expira_en=ahora + timezone.timedelta(minutes=10),
    )
    CodigoAcceso.objects.create(
        email="juan@gmail.com", codigo_hash="b" * 64,
        expira_en=ahora + timezone.timedelta(minutes=10),
    )
    assert CodigoAcceso.objects.filter(
        email="juan@gmail.com", usado_en__isnull=True,
    ).count() == 2
