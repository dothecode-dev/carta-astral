"""El reparto de temas del informe largo (spec 2026-10-07, RF1-RF5).

FIXTURE SINTÉTICO: reproduce la ESTRUCTURA del caso real que motivó el
cambio (cúmulo en casa X con conjunciones al Medio Cielo, Luna ☍ Mercurio a
5,8°, Sol ☍ Neptuno a 5,6°) con posiciones inventadas. Nunca pegar acá los
datos de una carta real: el repo es público y las posiciones exactas
permiten recalcular fecha, hora y lugar de nacimiento.
"""

from interpret.reparto import temas


def _p(name, sign, house):
    return {"name": name, "sign": sign, "house": house}


def _a(p1, aspect, p2, orbit):
    return {"p1": p1, "p2": p2, "aspect": aspect, "orbit": orbit, "movement": "Applying"}


CARTA = {
    "time_known": True,
    "placements": [
        _p("Sun", "Leo", "Eleventh_House"),
        _p("Moon", "Aqu", "Fifth_House"),
        _p("Mercury", "Vir", "Tenth_House"),
        _p("Venus", "Lib", "Tenth_House"),
        _p("Mars", "Lib", "Tenth_House"),
        _p("Jupiter", "Pis", "Twelfth_House"),
        _p("Saturn", "Can", "Second_House"),
        _p("Uranus", "Cap", "Fourth_House"),
        _p("Neptune", "Tau", "Sixth_House"),
        _p("Pluto", "Sag", "Third_House"),
        _p("Chiron", "Vir", "Tenth_House"),
    ],
    "angles": [
        {"name": "Ascendant", "sign": "Sag", "abs_pos": 250.0},
        {"name": "Medium_Coeli", "sign": "Lib", "abs_pos": 190.0},
        {"name": "Descendant", "sign": "Gem", "abs_pos": 70.0},
        {"name": "Imum_Coeli", "sign": "Ari", "abs_pos": 10.0},
    ],
    "aspects": [
        _a("Venus", "conjunction", "Mars", 0.90),
        _a("Venus", "conjunction", "Medium_Coeli", 1.30),
        _a("Mars", "conjunction", "Medium_Coeli", 2.60),
        _a("Sun", "trine", "Pluto", 1.90),
        _a("Sun", "sextile", "Saturn", 2.40),
        _a("Sun", "conjunction", "Jupiter", 3.10),
        _a("Mercury", "square", "Saturn", 3.20),
        _a("Uranus", "trine", "Ascendant", 4.40),
        _a("Sun", "opposition", "Neptune", 5.60),
        _a("Moon", "opposition", "Mercury", 5.80),
        # Los que NO entran:
        _a("Mercury", "opposition", "Uranus", 7.30),  # orbe > 5
        _a("Saturn", "square", "Uranus", 3.90),  # sin extremo personal
        _a("Saturn", "quintile", "Imum_Coeli", 0.70),  # tipo menor
        _a("Chiron", "sextile", "Ascendant", 0.40),  # Quirón no es tema
        _a("Venus", "opposition", "Imum_Coeli", 1.30),  # IC no es tema
        _a("Mars", "trine", "Neptune", 5.30),  # 5,3° sin Sol ni Luna
    ],
}

CARTA_SIN_HORA = {
    "time_known": False,
    "angles": None,
    "aspects": [],
    "placements": [{**p, "house": None} for p in CARTA["placements"]],
}


def _sin_mercurio_en_x(carta):
    return {**carta, "placements": [
        p if p["name"] != "Mercury" else {**p, "house": "Ninth_House"} for p in carta["placements"]
    ]}


def _por_clave(lista):
    return {t.clave: t for t in lista}


def test_luna_mercurio_a_5_8_entra_y_es_de_tensiones():
    t = _por_clave(temas(CARTA))
    assert t["aspecto:Moon|opposition|Mercury"].duena == "tensiones"


def test_sol_neptuno_a_5_6_entra_por_el_orbe_del_sol():
    assert _por_clave(temas(CARTA))["aspecto:Sun|opposition|Neptune"].duena == "tensiones"


def test_los_aspectos_que_no_califican_no_son_temas():
    claves = set(_por_clave(temas(CARTA)))
    for fuera in (
        "aspecto:Mercury|opposition|Uranus",
        "aspecto:Saturn|square|Uranus",
        "aspecto:Saturn|quintile|Imum_Coeli",
        "aspecto:Chiron|sextile|Ascendant",
        "aspecto:Venus|opposition|Imum_Coeli",
        "aspecto:Mars|trine|Neptune",
    ):
        assert fuera not in claves, fuera


def test_el_cumulo_de_casa_x_es_de_trabajo_y_absorbe_sus_conjunciones():
    t = _por_clave(temas(CARTA))
    cumulo = t["cumulo:Tenth_House"]
    assert cumulo.duena == "trabajo"
    assert cumulo.puntos == ("Mercury", "Venus", "Mars")
    assert set(cumulo.internos) == {
        ("Venus", "conjunction", "Mars"),
        ("Venus", "conjunction", "Medium_Coeli"),
        ("Mars", "conjunction", "Medium_Coeli"),
    }
    # Absorbidos: no aparecen además como aspectos sueltos.
    assert "aspecto:Venus|conjunction|Mars" not in t
    assert "aspecto:Mars|conjunction|Medium_Coeli" not in t


def test_dos_planetas_en_una_casa_no_son_cumulo():
    assert not [x for x in temas(_sin_mercurio_en_x(CARTA)) if x.tipo == "cumulo"]


def test_quiron_no_cuenta_para_el_cumulo():
    # Venus, Mars y Quirón en X: dos planetas más Quirón no hacen cúmulo.
    assert "cumulo:Tenth_House" not in _por_clave(temas(_sin_mercurio_en_x(CARTA)))


def test_duena_del_cumulo_segun_la_casa():
    from interpret.reparto import DUENA_CASA

    assert DUENA_CASA == {
        "First_House": "firma", "Second_House": "trabajo", "Third_House": "mente",
        "Fourth_House": "casas", "Fifth_House": "afectos", "Sixth_House": "trabajo",
        "Seventh_House": "afectos", "Eighth_House": "casas", "Ninth_House": "casas",
        "Tenth_House": "trabajo", "Eleventh_House": "casas", "Twelfth_House": "casas",
    }


def test_planetas_y_angulos_con_su_duena():
    t = _por_clave(temas(CARTA))
    esperado = {
        "Sun": "firma", "Moon": "firma", "Ascendant": "firma",
        "Mercury": "mente", "Venus": "afectos",
        "Mars": "trabajo", "Saturn": "trabajo", "Medium_Coeli": "trabajo",
        "Jupiter": "lentos", "Uranus": "lentos", "Neptune": "lentos", "Pluto": "lentos",
    }
    for punto, duena in esperado.items():
        assert t[f"planeta:{punto}"].duena == duena, punto
    assert "planeta:Chiron" not in t


def test_aspectos_sueltos_suaves_van_al_extremo_mas_personal():
    t = _por_clave(temas(CARTA))
    assert t["aspecto:Sun|trine|Pluto"].duena == "firma"
    assert t["aspecto:Uranus|trine|Ascendant"].duena == "firma"
    assert t["aspecto:Mercury|square|Saturn"].duena == "tensiones"


def test_venus_marte_fuera_de_cumulo_es_de_afectos():
    assert _por_clave(temas(_sin_mercurio_en_x(CARTA)))["aspecto:Venus|conjunction|Mars"].duena == "afectos"


def test_sin_hora_no_hay_cumulos_ni_angulos_ni_aspectos():
    lista = temas(CARTA_SIN_HORA)
    assert {x.tipo for x in lista} == {"planeta"}
    claves = set(_por_clave(lista))
    assert "planeta:Ascendant" not in claves and "planeta:Medium_Coeli" not in claves


def test_es_determinista():
    assert temas(CARTA) == temas(CARTA)
    invertida = {**CARTA, "aspects": list(reversed(CARTA["aspects"]))}
    assert temas(invertida) == temas(CARTA)


def test_data_vacia_no_rompe():
    assert temas({}) == []
