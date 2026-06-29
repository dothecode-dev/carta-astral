import pytest
from django.core.management import CommandError, call_command

from api.geocode import search
from api.models import GeoName, GeoNameToken

pytestmark = pytest.mark.django_db


def _geoname_row(gid, name, asciiname, lat, lng, country, admin1_code, population, tz):
    # Fila de cities500.txt: 19 columnas tab-separated.
    cols = [""] * 19
    cols[0] = str(gid)
    cols[1] = name
    cols[2] = asciiname
    cols[4] = str(lat)
    cols[5] = str(lng)
    cols[8] = country
    cols[10] = admin1_code
    cols[14] = str(population)
    cols[17] = tz
    return "\t".join(cols)


SAMPLE_ROWS = [
    _geoname_row(3838583, "San Carlos de Bariloche", "San Carlos de Bariloche",
                 -41.13345, -71.30979, "AR", "17", 108205, "America/Argentina/Salta"),
    _geoname_row(3435910, "Córdoba", "Cordoba", -31.4135, -64.18105, "AR", "07",
                 1430023, "America/Argentina/Cordoba"),
    _geoname_row(2519354, "Córdoba", "Cordoba", 37.89155, -4.77275, "ES", "51",
                 325708, "Europe/Madrid"),
    _geoname_row(3133895, "Tromsø", "Tromso", 69.6489, 18.95508, "NO", "20",
                 36088, "Europe/Oslo"),
    _geoname_row(2867714, "München", "Munchen", 48.13743, 11.57549, "DE", "02",
                 1260391, "Europe/Berlin"),
]

# admin1CodesASCII.txt: "AR.17\tRío Negro\tRio Negro\t<gid>"
SAMPLE_ADMIN1 = [
    "AR.17\tRío Negro\tRio Negro\t3855065",
    "AR.07\tCordoba\tCordoba\t3860259",
    "ES.51\tAndalusia\tAndalusia\t2593109",
]


@pytest.fixture
def sample_files(tmp_path):
    geo = tmp_path / "cities.txt"
    geo.write_text("\n".join(SAMPLE_ROWS) + "\n", encoding="utf-8")
    adm = tmp_path / "admin1.txt"
    adm.write_text("\n".join(SAMPLE_ADMIN1) + "\n", encoding="utf-8")
    return geo, adm


def test_import_loads_all_cities(sample_files):
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    assert GeoName.objects.count() == 5
    bari = GeoName.objects.get(geonameid=3838583)
    assert bari.name == "San Carlos de Bariloche"
    assert bari.population == 108205
    assert bari.tz_geonames == "America/Argentina/Salta"


def test_import_builds_tokens_from_names(sample_files):
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    bari = GeoName.objects.get(geonameid=3838583)
    assert set(bari.tokens.values_list("token", flat=True)) == {"san", "carlos", "de", "bariloche"}
    # Tromsø debe tokenizarse a 'tromso' (unidecode).
    tromso = GeoName.objects.get(geonameid=3133895)
    assert list(tromso.tokens.values_list("token", flat=True)) == ["tromso"]


def test_import_resolves_admin1_name(sample_files):
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    bari = GeoName.objects.get(geonameid=3838583)
    assert bari.admin1 == "Río Negro"


def test_import_is_idempotent(sample_files):
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    assert GeoName.objects.count() == 5
    assert GeoNameToken.objects.filter(geoname__geonameid=3838583).count() == 4


def test_import_applies_exonyms(sample_files):
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    # 'munich' es exónimo curado de München (gid 2867714, presente en el sample).
    assert search("munich")[0]["name"] == "München"


def test_exonym_pointing_to_absent_city_is_skipped(sample_files, tmp_path):
    # Si el geonameid del exónimo no está en el dataset cargado, no debe romper.
    geo, adm = sample_files
    call_command("import_geonames", file=str(geo), admin1_file=str(adm))
    # 'londres'→London no está en el sample; no debe haber crash ni match.
    assert search("londres") == []


def test_import_missing_file_raises_cleanly(tmp_path):
    with pytest.raises(CommandError):
        call_command("import_geonames", file=str(tmp_path / "nope.txt"))
