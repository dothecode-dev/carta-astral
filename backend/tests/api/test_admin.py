"""El admin de consulta: que no edite y que no filtre datos de nacimiento.

Un panel web sobre la base de producción es una superficie nueva. Estos tests
fijan sus dos límites: es de sólo lectura, y no muestra nombre, fecha, hora ni
lugar de nacimiento — lo mismo que la privacy policy promete y que el scrubbing
de Sentry ya protege.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import NoReverseMatch, clear_url_caches, reverse

from api.admin import ChartAdmin, InterpretationAdmin
from api.chart_service import create_chart
from api.models import (
    Account,
    BirthData,
    Chart,
    CreditTransaction,
    Derecho,
    Interpretation,
    Movimiento,
)


# El admin sirve su CSS con CompressedManifestStaticFilesStorage, que exige el
# manifiesto ya generado: sin esto, cualquier test que renderice una página del
# admin muere con "Missing staticfiles manifest entry". Se evita depender de
# haber corrido collectstatic (que además está gitignorado, así que en un clon
# limpio no existe).
sin_manifiesto = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    ALLOWED_HOSTS=["testserver"],
)


@pytest.fixture
def admin_montado(monkeypatch):
    """Monta el admin en una ruta conocida recargando el urlconf."""
    import importlib

    import config.urls

    monkeypatch.setenv("ADMIN_URL", "panel-test")
    importlib.reload(config.urls)
    clear_url_caches()
    yield
    monkeypatch.delenv("ADMIN_URL", raising=False)
    importlib.reload(config.urls)
    clear_url_caches()


@pytest.mark.parametrize(
    "modelo", [Account, Chart, Interpretation, CreditTransaction, Derecho, Movimiento],
)
def test_ningun_modelo_se_puede_crear_editar_ni_borrar(modelo):
    """Las mutaciones van por management command, no por el panel.

    Se usan las instancias REGISTRADAS (no una construida a mano) para que el
    test valide lo que el admin realmente expone.
    """
    from django.contrib import admin as dj_admin

    registrado = dj_admin.site._registry[modelo]

    assert registrado.has_add_permission(None) is False
    assert registrado.has_change_permission(None) is False
    assert registrado.has_delete_permission(None) is False


@pytest.mark.django_db
@sin_manifiesto
def test_la_ficha_de_una_cuenta_muestra_lo_que_puede_usar(admin_montado):
    """Sin esto el panel quedó ciego: al salir los dos contadores viejos de
    `AccountAdmin` no entró nada que respondiera "qué le queda a esta cuenta",
    y contestar un "no me acreditaron" obligaba a sumar `Movimiento` a ojo.

    Se RENDERIZA la ficha en vez de mirar la configuración: un inline mal
    declarado (una FK ambigua, un campo que no existe) explota al dibujarse,
    no al registrarse, y un test que sólo lea `inlines` no lo vería."""
    from api import canje

    acc = Account.objects.create(email="u@x.com")
    canje.otorgar(acc, "informe_natal", 4, origen="compra", external_id="evt_ficha")
    staff = User.objects.create_superuser("staff3", "s3@x.com", "pw-de-test-12345")
    c = Client()
    # force_login: ver comentario en test_un_staff_ve_las_cuentas_pero_no_los_datos_de_nacimiento.
    c.force_login(staff)

    r = c.get(f"/panel-test/api/account/{acc.pk}/change/")

    assert r.status_code == 200
    cuerpo = r.content.decode().lower()
    # Los tres bloques por su encabezado, no por el contenido: `informe_natal`
    # aparece igual en el movimiento, así que buscarlo no distinguiría si el
    # inline de derechos se cayó.
    assert "derechos" in cuerpo  # qué puede usar
    assert "movimientos" in cuerpo  # por qué le quedó eso
    assert "cantidad restante" in cuerpo  # la columna del derecho, ya dibujada
    assert "evt_ficha" in cuerpo


@pytest.mark.django_db
@sin_manifiesto
def test_los_derechos_se_pueden_buscar_por_producto(admin_montado):
    """La otra pregunta: "¿quién tiene un pack sin usar?", que se contesta
    desde el changelist de `Derecho` y no desde una cuenta puntual."""
    from api import canje

    acc = Account.objects.create(email="d@x.com")
    canje.otorgar(acc, "informe_natal", 2, origen="compra", external_id="evt_lista")
    staff = User.objects.create_superuser("staff4", "s4@x.com", "pw-de-test-12345")
    c = Client()
    c.force_login(staff)

    r = c.get("/panel-test/api/derecho/")

    assert r.status_code == 200
    assert "informe_natal" in r.content.decode()


def test_la_ficha_de_cuenta_muestra_la_deuda():
    """`deuda` es lo que la cuenta debe tras un reembolso de algo que ya
    consumió: desde que salieron los dos contadores viejos era el único
    número de plata que no aparecía en ningún lado del panel."""
    from django.contrib import admin as dj_admin

    assert "deuda" in dj_admin.site._registry[Account].list_display


def test_birthdata_no_esta_registrado():
    """El modelo con nombre, fecha, hora y coordenadas no se expone."""
    from django.contrib import admin as dj_admin

    assert BirthData not in dj_admin.site._registry


def test_el_admin_de_cartas_no_expone_datos_de_nacimiento():
    """Ni por los campos del formulario ni por `data`, que es el JSON
    astronómico del que se puede reconstruir el momento y el lugar."""
    campos = set(ChartAdmin.fields) | set(ChartAdmin.list_display)

    assert "data" not in campos
    assert "birth_data" not in campos
    for prohibido in ("name", "date", "time", "lat", "lng", "place_label"):
        assert prohibido not in campos


def test_el_admin_de_interpretaciones_no_expone_el_texto():
    """La lectura habla de la persona; para operar no hace falta leerla."""
    campos = set(InterpretationAdmin.fields) | set(InterpretationAdmin.list_display)

    assert "text" not in campos


@pytest.mark.django_db
def test_sin_ADMIN_URL_el_panel_no_existe():
    """Si un despliegue no setea la variable, no hay panel que atacar."""
    with pytest.raises(NoReverseMatch):
        reverse("admin:index")


@pytest.mark.django_db
def test_el_panel_pide_login(admin_montado):
    r = Client().get("/panel-test/")

    assert r.status_code in (301, 302)
    assert "login" in r["Location"]


@pytest.mark.django_db
@sin_manifiesto
def test_un_staff_ve_las_cuentas_pero_no_los_datos_de_nacimiento(admin_montado):
    acc = Account.objects.create(email="u@x.com")
    create_chart(
        {
            "name": "Ceci",
            "date": "1993-03-21",
            "time": "08:45",
            "time_known": True,
            "lat": -34.6,
            "lng": -58.4,
            "place_label": "Buenos Aires",
        },
        acc,
    )
    staff = User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
    c = Client()
    # force_login en vez de login: django-axes exige un `request` real en
    # authenticate(), y Client.login() no lo pasa. No es una regresión de
    # producción (el login real sí manda request) — es que login() cambió de
    # contrato al agregar axes. force_login no pasa por las auth backends,
    # así que no interactúa con axes; lo que este test verifica (permisos y
    # scrubbing de datos) no depende de cómo se estableció la sesión.
    #
    # Que el login REAL sigue andando con axes en la cadena de backends —y a
    # quién bloquea— lo cubre `tests/api/test_login_axes.py`, que le pega al
    # formulario del admin con POST: acá no queda esa superficie sin probar.
    c.force_login(staff)

    listado = c.get("/panel-test/api/chart/")

    assert listado.status_code == 200
    cuerpo = listado.content.decode()
    assert "Ceci" not in cuerpo
    assert "Buenos Aires" not in cuerpo
    assert "-34.6" not in cuerpo


@pytest.mark.django_db
@sin_manifiesto
def test_el_canje_se_ve_para_investigar_un_no_me_acreditaron(admin_montado):
    acc = Account.objects.create(email="u@x.com")
    from api import canje

    canje.otorgar(acc, "informe_natal", 10, origen="compra",
                  external_id="evt_visible", note="revenuecat:credits_10")
    staff2 = User.objects.create_superuser("staff2", "s2@x.com", "pw-de-test-12345")
    c = Client()
    # force_login: ver comentario en test_un_staff_ve_las_cuentas_pero_no_los_datos_de_nacimiento.
    c.force_login(staff2)

    r = c.get("/panel-test/api/movimiento/")

    assert r.status_code == 200
    assert "evt_visible" in r.content.decode()


@pytest.mark.django_db
def test_los_modelos_de_geonames_no_se_registran():
    """Millones de filas de un dataset público: no aportan nada operativo."""
    from django.contrib import admin as dj_admin

    from api.models import GeoName, GeoNameToken

    assert GeoName not in dj_admin.site._registry
    assert GeoNameToken not in dj_admin.site._registry


@pytest.mark.django_db
def test_los_modelos_que_si_importan_estan_registrados():
    from django.contrib import admin as dj_admin

    for modelo in (Account, Chart, Interpretation):
        assert modelo in dj_admin.site._registry
