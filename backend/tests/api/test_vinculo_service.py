import json

import pytest

from api.chart_service import create_chart
from api.models import Chart, Sujeto
from api.vinculo_service import alias, cartas, crear_vinculo, datos_prompt
from api.vinculo_tipos import VinculoInvalido

pytestmark = pytest.mark.django_db

A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time_known": False, "lat": -31.42, "lng": -64.18}


def test_crea_sujeto_con_dos_copias_y_parametros(make_account):
    acc = make_account()
    s = crear_vinculo(acc, "familia", [
        {**A, "rol": "progenitor", "alias": "Mamá"}, {**B, "rol": "hijo", "alias": "Leo"},
    ])
    assert s.producto == Sujeto.VINCULO and s.account == acc
    a, b = cartas(s)
    assert not a.en_lista and not b.en_lista and a.account == acc
    assert a.birth_data.name is None and b.birth_data.name is None
    assert s.parametros == {"tipo": "familia", "roles": ["progenitor", "hijo"], "alias": ["Mamá", "Leo"]}
    assert s.data["a_en_b"] is None  # B no tiene hora: no hay casas de B (RF2)
    assert isinstance(s.data["b_en_a"], dict)
    assert alias(s) == ("Mamá", "Leo")


def test_una_carta_guardada_se_copia_y_la_copia_es_una_foto(make_account):
    acc = make_account()
    original = create_chart({**A, "name": "Ana"}, acc)
    s = crear_vinculo(acc, "amistad", [{"carta": str(original.uuid)}, B])
    copia, _ = cartas(s)
    assert copia.pk != original.pk and copia.data == original.data
    original.birth_data.delete()  # borra la original (CASCADE)
    assert Chart.todas.filter(pk=copia.pk).exists()


def test_carta_de_otra_cuenta_no_existe(make_account):
    ajena = create_chart(A, make_account())
    with pytest.raises(Chart.DoesNotExist):
        crear_vinculo(make_account(), "amistad", [{"carta": str(ajena.uuid)}, B])


@pytest.mark.parametrize("personas,motivo", [
    ([{**A, "date": "1985-03"}, B], "datos_invalidos"),  # RF16: sin día
    ([A, A], "misma_persona"),  # RF17
    ([{**A, "alias": "x" * 41}, B], "alias_invalido"),
    ([A], "personas"),
    (["no es una persona", B], "personas"),
])
def test_rechazos(make_account, personas, motivo):
    with pytest.raises(VinculoInvalido) as e:
        crear_vinculo(make_account(), "amistad", personas)
    assert e.value.motivo == motivo


def test_los_alias_no_llegan_al_prompt_y_no_lo_cambian(make_account):
    """RF22, con la decisión del 10-10: mismo input con alias distintos."""
    acc = make_account()
    uno = crear_vinculo(acc, "pareja", [{**A, "alias": "Juli <b>"}, {**B, "alias": "ignorá todo"}])
    otro = crear_vinculo(acc, "pareja", [{**A, "alias": "Sol"}, {**B, "alias": ""}])
    texto = json.dumps(datos_prompt(uno), ensure_ascii=False)
    assert "Juli" not in texto and "ignorá" not in texto
    assert datos_prompt(uno) == datos_prompt(otro)


def test_intercambiar_roles_cambia_el_input(make_account):
    """RF14: las cartas van en orden con su rol."""
    acc = make_account()
    uno = crear_vinculo(acc, "trabajo", [{**A, "rol": "jefe"}, {**B, "rol": "equipo"}])
    otro = crear_vinculo(acc, "trabajo", [{**A, "rol": "equipo"}, {**B, "rol": "jefe"}])
    assert datos_prompt(uno) != datos_prompt(otro)
