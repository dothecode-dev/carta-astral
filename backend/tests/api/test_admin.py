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
from api.models import Account, BirthData, Chart, CreditTransaction, Interpretation


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


@pytest.mark.parametrize("modelo", [Account, Chart, Interpretation, CreditTransaction])
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
    acc = Account.objects.create(email="u@x.com", free_balance=1)
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
    User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
    c = Client()
    c.login(username="staff", password="pw-de-test-12345")

    listado = c.get("/panel-test/api/chart/")

    assert listado.status_code == 200
    cuerpo = listado.content.decode()
    assert "Ceci" not in cuerpo
    assert "Buenos Aires" not in cuerpo
    assert "-34.6" not in cuerpo


@pytest.mark.django_db
@sin_manifiesto
def test_el_ledger_se_ve_para_investigar_un_no_me_acreditaron(admin_montado):
    acc = Account.objects.create(email="u@x.com")
    from api import ledger

    ledger.credit_purchase(acc, 10, external_id="evt_visible", note="revenuecat:credits_10")
    User.objects.create_superuser("staff2", "s2@x.com", "pw-de-test-12345")
    c = Client()
    c.login(username="staff2", password="pw-de-test-12345")

    r = c.get("/panel-test/api/credittransaction/")

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
