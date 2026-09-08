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


def test_una_direccion_no_puede_tener_dos_codigos_vigentes():
    """Lo sostiene una UniqueConstraint parcial sobre (email) donde usado_en es
    NULL y expira_en > ahora. En SQLite la semántica es otra: este test vale en
    Postgres, que es contra lo que corre el CI."""
    ahora = timezone.now()
    CodigoAcceso.objects.create(
        email="juan@gmail.com", codigo_hash="a" * 64,
        expira_en=ahora + timezone.timedelta(minutes=10),
    )
    with pytest.raises(Exception):
        CodigoAcceso.objects.create(
            email="juan@gmail.com", codigo_hash="b" * 64,
            expira_en=ahora + timezone.timedelta(minutes=10),
        )
