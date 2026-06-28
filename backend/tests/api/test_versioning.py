from api.versioning import engine_version


def test_engine_version_names_both_libraries():
    v = engine_version()
    assert "kerykeion" in v
    assert "pyswisseph" in v
