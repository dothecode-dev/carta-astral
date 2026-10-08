import pytest
from django.core.exceptions import ImproperlyConfigured

from config import caches


def test_la_cache_de_la_base_no_poda_a_las_300():
    conf = caches.armar(usar_db=True, debug=False)
    assert conf["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    assert conf["default"]["OPTIONS"]["MAX_ENTRIES"] == caches.MAX_ENTRIES >= 100_000


def test_produccion_sin_cache_compartida_no_arranca():
    with pytest.raises(ImproperlyConfigured):
        caches.armar(usar_db=False, debug=False)


def test_desarrollo_sin_db_usa_locmem():
    conf = caches.armar(usar_db=False, debug=True)
    assert conf["default"]["BACKEND"].endswith("LocMemCache")
