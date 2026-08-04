"""Las guardas de configuración que sólo importan en producción.

Ninguna estaba testeada. Son fail-closed: si se rompen, no se cae nada — se
degrada en silencio a una configuración insegura, que es peor, porque nadie se
entera hasta que pasa algo.

El caso más caro es el CORS: `DevCorsMiddleware` abre la API a cualquier
origen y sólo debe montarse con DEBUG. Si un día alguien invierte esa condición
o la borra, esta suite lo detecta.
"""

import importlib
import os

import pytest
from django.core.exceptions import ImproperlyConfigured


def _cargar_settings(monkeypatch, **env):
    """Reimporta config.settings con el entorno dado.

    Los settings se evalúan al importarse (no hay una función de fábrica), así
    que la única forma de probar las ramas de producción es recargar el módulo.
    """
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import config.settings as s

    return importlib.reload(s)


PROD_MINIMO = {
    "DEBUG": "",
    "SECRET_KEY": "no-es-la-de-prod-pero-existe",
    "ALLOWED_HOSTS": "api.ejemplo.com",
    "USE_DB_CACHE": "1",
    "WAGTAILADMIN_BASE_URL": "https://cms.ejemplo.com",
    "WEB_BASE_URL": "https://web.ejemplo.com",
}


def test_el_cors_abierto_NO_se_monta_en_produccion(monkeypatch):
    """El fail-closed más riesgoso: CORS `*` filtrado a prod expone la API."""
    s = _cargar_settings(monkeypatch, **PROD_MINIMO)

    assert "config.middleware.DevCorsMiddleware" not in s.MIDDLEWARE


def test_el_cors_abierto_si_esta_en_desarrollo(monkeypatch):
    """El contrapunto: si tampoco estuviera en dev, el test de arriba pasaría
    por la razón equivocada (por ejemplo si alguien borra el middleware)."""
    s = _cargar_settings(monkeypatch, DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None)

    assert "config.middleware.DevCorsMiddleware" in s.MIDDLEWARE


def test_sin_secret_key_en_produccion_no_arranca(monkeypatch):
    """Fail-fast: mejor no levantar que levantar con una clave de juguete."""
    with pytest.raises(ImproperlyConfigured):
        _cargar_settings(monkeypatch, DEBUG="", SECRET_KEY=None, ALLOWED_HOSTS="x.com")


def test_allowed_hosts_no_es_comodin_en_produccion(monkeypatch):
    s = _cargar_settings(monkeypatch, **PROD_MINIMO)

    assert s.ALLOWED_HOSTS == ["api.ejemplo.com"]
    assert "*" not in s.ALLOWED_HOSTS


def test_el_hardening_de_cookies_y_hsts_se_activa_en_produccion(monkeypatch):
    s = _cargar_settings(monkeypatch, **PROD_MINIMO)

    assert s.SESSION_COOKIE_SECURE is True
    assert s.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert s.SECURE_HSTS_SECONDS > 0


def test_en_desarrollo_allowed_hosts_es_permisivo(monkeypatch):
    s = _cargar_settings(monkeypatch, DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None)

    assert s.ALLOWED_HOSTS == ["*"]


def test_el_mapa_de_productos_de_revenuecat_tolera_estar_vacio(monkeypatch):
    """Sin la env var el backend tiene que arrancar igual (webhook fail-closed),
    no morir al importar los settings."""
    s = _cargar_settings(monkeypatch, DEBUG="1", REVENUECAT_PRODUCT_CREDITS=None)

    assert s.REVENUECAT_PRODUCT_CREDITS == {}


def test_el_cache_compartido_es_obligatorio_en_produccion(monkeypatch):
    """LocMem en prod rompe el cap de costo, el throttle y el lock de
    interpretación: cada worker tendría su propio contador. El propio comentario
    de settings.py lo advertía, pero nada lo impedía."""
    with pytest.raises(ImproperlyConfigured):
        _cargar_settings(
            monkeypatch,
            DEBUG="",
            SECRET_KEY="existe",
            ALLOWED_HOSTS="x.com",
            USE_DB_CACHE=None,
        )


def test_sin_wagtailadmin_base_url_en_produccion_no_arranca(monkeypatch):
    """Fail-fast: sin esta var, la API del CMS arma `full_url` apuntando a
    localhost y las portadas de las notas salen rotas en la web, sin ningún
    error visible (B2 de la revisión final)."""
    with pytest.raises(ImproperlyConfigured):
        _cargar_settings(monkeypatch, **{**PROD_MINIMO, "WAGTAILADMIN_BASE_URL": None})


def test_wagtailadmin_base_url_viene_del_entorno_en_produccion(monkeypatch):
    s = _cargar_settings(
        monkeypatch, **{**PROD_MINIMO, "WAGTAILADMIN_BASE_URL": "https://cms.dothecode.dev"}
    )

    assert s.WAGTAILADMIN_BASE_URL == "https://cms.dothecode.dev"


def test_wagtailadmin_base_url_apunta_a_localhost_en_desarrollo(monkeypatch):
    """En DEBUG sí puede haber default a localhost: es lo correcto en dev."""
    s = _cargar_settings(
        monkeypatch, DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None, WAGTAILADMIN_BASE_URL=None
    )

    assert s.WAGTAILADMIN_BASE_URL == "http://localhost:8000"


def test_sin_web_base_url_en_produccion_no_arranca(monkeypatch):
    """Fail-fast: sin esta var, los enlaces internos del cuerpo de una nota
    (RichTextAPIField, ver cms/wagtail_hooks.py) resolverían contra
    localhost:3000 en la web publicada (B3, ronda 2 de la revisión final)."""
    with pytest.raises(ImproperlyConfigured):
        _cargar_settings(monkeypatch, **{**PROD_MINIMO, "WEB_BASE_URL": None})


def test_web_base_url_viene_del_entorno_en_produccion(monkeypatch):
    s = _cargar_settings(
        monkeypatch, **{**PROD_MINIMO, "WEB_BASE_URL": "https://cartaastral.app"}
    )

    assert s.WEB_BASE_URL == "https://cartaastral.app"


def test_web_base_url_apunta_al_dev_server_de_next_en_desarrollo(monkeypatch):
    """En DEBUG sí puede haber default: es el puerto de `next dev` (web/package.json)."""
    s = _cargar_settings(
        monkeypatch, DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None, WEB_BASE_URL=None
    )

    assert s.WEB_BASE_URL == "http://localhost:3000"


def test_media_root_en_produccion_es_el_volumen_persistente(monkeypatch):
    s = _cargar_settings(monkeypatch, **PROD_MINIMO, MEDIA_ROOT=None)

    assert s.MEDIA_ROOT == "/data/media"


def test_media_root_en_desarrollo_no_apunta_a_la_raiz_del_disco(monkeypatch):
    """`/data/media` no existe ni es escribible en una Mac.

    Con el default anterior (sin rama de DEBUG), subir una portada desde el
    panel en local moría con PermissionError al intentar crear el directorio
    en la raíz del disco. Los tests no lo veían porque todos pisan MEDIA_ROOT
    con `tmp_path`.
    """
    s = _cargar_settings(
        monkeypatch, DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None, MEDIA_ROOT=None
    )

    assert s.MEDIA_ROOT == str(s.BASE_DIR / "media")


@pytest.fixture(autouse=True)
def _restaurar_settings():
    """Deja config.settings como estaba: si no, los tests que corren después
    heredan el entorno recargado y fallan por contagio.

    DEBUG=1 explícito porque este teardown corre ANTES de que monkeypatch
    restaure el entorno: sin esto, la recarga vuelve a disparar el fail-fast
    del test de SECRET_KEY y el error aparece en el teardown.
    """
    yield
    os.environ["DEBUG"] = "1"
    import config.settings

    importlib.reload(config.settings)
