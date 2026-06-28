from importlib.metadata import version


def engine_version() -> str:
    return f"kerykeion {version('kerykeion')} / pyswisseph {version('pyswisseph')}"
