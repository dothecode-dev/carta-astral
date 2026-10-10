import pytest

from api.vinculo_tipos import VinculoInvalido, validar


@pytest.mark.parametrize("tipo,a,b", [
    ("trabajo", "jefe", "equipo"), ("trabajo", "equipo", "jefe"),
    ("trabajo", "socio", "socio"), ("trabajo", "colega", "colega"),
    ("familia", "progenitor", "hijo"), ("familia", "hijo", "progenitor"),
    ("familia", "hermano", "hermano"), ("familia", "otro_familiar", "otro_familiar"),
])
def test_combinaciones_validas(tipo, a, b):
    assert validar(tipo, a, b) == (a, b)


@pytest.mark.parametrize("tipo", ["pareja", "amistad"])
def test_pareja_y_amistad_no_llevan_rol(tipo):
    assert validar(tipo, "", "") == ("", "")
    with pytest.raises(VinculoInvalido) as e:
        validar(tipo, "jefe", "equipo")
    assert e.value.motivo == "rol_invalido"


@pytest.mark.parametrize("tipo,a,b,motivo", [
    ("vecinos", "", "", "tipo_invalido"),
    ("trabajo", "progenitor", "hijo", "rol_invalido"),
    ("familia", "progenitor", "progenitor", "combinacion_invalida"),
    ("trabajo", "jefe", "jefe", "combinacion_invalida"),
    ("trabajo", "", "equipo", "rol_invalido"),
])
def test_rechazos(tipo, a, b, motivo):
    with pytest.raises(VinculoInvalido) as e:
        validar(tipo, a, b)
    assert e.value.motivo == motivo
