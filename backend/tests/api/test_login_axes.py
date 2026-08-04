"""El login del admin, ejercitado de verdad: credenciales, bloqueo y de quién.

Los dos tests que hacían `Client.login()` pasaron a `force_login` cuando se
agregó django-axes (axes exige un `request` real en `authenticate()`, y
`login()` no lo pasa). `force_login` establece la sesión a mano y no toca
`AUTHENTICATION_BACKENDS`: desde ese cambio, ningún test de la suite recorría
el camino de autenticación por password — justo el que ese mismo diff modificó
al insertar `AxesStandaloneBackend` al frente de la cadena. Esto lo repone.

Lo que se prueba acá es el formulario real del admin, con POST y todo, porque
lo que puede romperse (backend mal configurado, tablas de axes sin migrar,
lockout que bloquea a quien no debe) sólo se ve pegándole a la vista.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from config.axes_ip import ip_del_cliente

# El admin sirve su CSS con CompressedManifestStaticFilesStorage, que exige el
# manifiesto ya generado: ver el mismo bloque en tests/api/test_admin.py.
sin_manifiesto = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    ALLOWED_HOSTS=["testserver"],
)

CLAVE = "pw-de-test-12345"


@pytest.fixture
def admin_montado(monkeypatch):
    """Monta el admin en una ruta conocida recargando el urlconf."""
    import importlib

    import config.urls

    monkeypatch.setenv("ADMIN_URL", "panel-test")
    importlib.reload(config.urls)
    from django.urls import clear_url_caches

    clear_url_caches()
    yield
    monkeypatch.delenv("ADMIN_URL", raising=False)
    importlib.reload(config.urls)
    clear_url_caches()


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("staff", "s@x.com", CLAVE)


def _login(client, clave=CLAVE, ip="203.0.113.9"):
    """Un POST al formulario real del admin, entrando por el proxy.

    `X-Forwarded-For` con una sola entrada es lo que produce Traefik para un
    cliente que no manda el header: la IP de la conexión que le llegó.
    """
    return client.post(
        "/panel-test/login/",
        {"username": "staff", "password": clave, "next": "/panel-test/"},
        HTTP_X_FORWARDED_FOR=ip,
    )


@pytest.mark.django_db
@sin_manifiesto
def test_el_login_real_con_la_clave_correcta_entra(admin_montado, staff):
    """Que axes esté en la cadena de backends no puede romper el login normal."""
    resp = _login(Client())

    assert resp.status_code == 302
    assert resp.headers["Location"] == "/panel-test/"


@pytest.mark.django_db
@sin_manifiesto
def test_cinco_intentos_fallidos_bloquean_a_ese_atacante(admin_montado, staff):
    c = Client()
    for _ in range(5):
        _login(c, clave="mal", ip="198.51.100.7")

    # Con la clave correcta y todo: el bloqueo es por IP, no por credencial.
    resp = _login(c, ip="198.51.100.7")

    # 429 y no 403: es el código que devuelve axes al estar bloqueado.
    assert resp.status_code == 429


@pytest.mark.django_db
@sin_manifiesto
def test_el_bloqueo_de_un_atacante_no_deja_afuera_al_resto(admin_montado, staff):
    """El corazón del arreglo.

    Sin `AXES_CLIENT_IP_CALLABLE`, axes lee `REMOTE_ADDR`, que detrás de
    Traefik es la IP del proxy para TODAS las requests: los cinco intentos de
    un bot cualquiera bloqueaban el admin para todo el mundo, el dueño
    incluido, durante `AXES_COOLOFF_TIME`. Con la IP real, el bloqueo cae
    sobre quien lo provocó.
    """
    atacante = Client()
    for _ in range(5):
        _login(atacante, clave="mal", ip="198.51.100.7")

    duenio = _login(Client(), ip="203.0.113.9")

    assert duenio.status_code == 302


@pytest.mark.django_db
@sin_manifiesto
def test_no_se_puede_evadir_el_bloqueo_falsificando_el_header(admin_montado, staff):
    """`X-Forwarded-For` lo puede escribir el cliente: la primera entrada es suya.

    Si se leyera la primera, un atacante manda `X-Forwarded-For: 1.2.3.4` y
    estrena IP en cada intento, con lo cual el lockout no existe. La última la
    escribe Traefik sobre lo que recibió, y es la que vale.
    """
    atacante = Client()
    for i in range(5):
        _login(atacante, clave="mal", ip=f"10.0.0.{i}, 198.51.100.7")

    resp = _login(atacante, ip="10.0.0.99, 198.51.100.7")

    assert resp.status_code == 429


def test_la_ip_es_la_ultima_del_header_y_cae_a_remote_addr():
    """El callable, sin pasar por el login: los tres casos que ve en producción."""

    class FakeRequest:
        def __init__(self, meta):
            self.META = meta

    directo = FakeRequest({"REMOTE_ADDR": "203.0.113.9"})
    por_traefik = FakeRequest(
        {"HTTP_X_FORWARDED_FOR": "203.0.113.9", "REMOTE_ADDR": "172.18.0.2"}
    )
    header_falsificado = FakeRequest(
        {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 203.0.113.9", "REMOTE_ADDR": "172.18.0.2"}
    )

    assert ip_del_cliente(directo) == "203.0.113.9"
    assert ip_del_cliente(por_traefik) == "203.0.113.9"
    assert ip_del_cliente(header_falsificado) == "203.0.113.9"
