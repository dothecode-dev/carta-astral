import pytest
from api.models import Interpretation
from api.sujetos import sujeto_natal
from interpret.trato import TRATOS

pytestmark = pytest.mark.django_db


def test_los_valores_del_trato():
    assert TRATOS == ("femenino", "masculino", "neutro")


def test_birthdata_e_interpretation_nacen_sin_trato(make_chart, make_account):
    account = make_account()
    carta = make_chart(account=account)
    assert carta.birth_data.trato == ""
    i = Interpretation.objects.create(
        sujeto=sujeto_natal(carta), lang="es",
        prompt_version="v2", tier="corto", text="",
    )
    assert i.trato == ""
