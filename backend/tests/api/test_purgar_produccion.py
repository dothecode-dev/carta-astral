"""Comando de purga del historial de producción (RF16), Task 17.

Se corre una sola vez, antes de deployar el código de dos tiers: borra las
cinco cuentas de prueba que hay en producción con el modelo viejo, para que
la migración del `unique_together` de `Interpretation` no caiga sobre filas
sin `tier`.
"""
import pytest
from django.core.management import call_command
from wagtail.models import Page

from api.auth import create_session
from api.models import (
    Account,
    BirthData,
    Chart,
    CreditTransaction,
    Device,
    GeoName,
    Interpretation,
    InterpretationSection,
    ProviderIdentity,
    Session,
    SubTombstone,
)
from cms.models import NoteIndexPage
from interpret.prompts import PROMPT_VERSION, SECCIONES


def _sembrar_cuenta_con_cartas_y_ledger(account):
    """Puebla los siete modelos que el comando debe purgar, más `BirthData` y
    `Device` (huérfanos, con FK SET_NULL a la cuenta): sin sembrar cada uno,
    un `count() == 0` después de purgar no prueba que el comando lo haya
    tocado."""
    bd = BirthData.objects.create(date="1990-05-20", lat=-34.6, lng=-58.4, tz_name="UTC")
    chart = Chart.objects.create(
        birth_data=bd, data={}, engine_version="test", account=account,
    )
    interpretacion = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, account=account, text="x",
    )
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0, texto="texto",
    )
    CreditTransaction.objects.create(
        account=account, kind="consumption", lot="paid", amount=-1, interpretation=interpretacion,
    )
    ProviderIdentity.objects.create(provider="google", sub="sub-de-prueba", account=account)
    Device.objects.create(account=account, platform="ios", push_token="tok-de-prueba")
    # Session es CASCADE (fix wave final / Minor de la revisión final): sin
    # sembrarla acá, un `count() == 0` de más abajo no distingue "el comando
    # la cuenta y la borra" de "nadie la mira y el CASCADE de Account la
    # limpia atrás, sin que el reporte lo diga".
    create_session(account)


@pytest.mark.django_db
def test_sin_el_flag_no_borra_nada(make_account, capsys):
    make_account()
    call_command("purgar_produccion")
    assert Account.objects.count() == 1
    assert "no se borró nada" in capsys.readouterr().out


@pytest.mark.django_db
def test_el_reporte_cuenta_session_aunque_se_borre_por_cascade(make_account, capsys):
    """Fix wave final / Minor: `Session` cuelga de `Account` con CASCADE, no
    con SET_NULL como los demás — borrar `Account` se la lleva puesta sin
    que el comando la nombre. Sin contarla, "esto es lo que se borraría" (y
    después "esto es lo que se borró") mentía por omisión sobre un modelo
    con datos de sesión que el comando sí destruye."""
    cuenta = make_account()
    create_session(cuenta)

    call_command("purgar_produccion")
    salida = capsys.readouterr().out
    assert "Session: 1" in salida

    call_command("purgar_produccion", "--si-estoy-seguro")
    salida = capsys.readouterr().out
    assert "Session: 1" in salida
    assert Session.objects.count() == 0


@pytest.mark.django_db
def test_con_el_flag_borra_todo_incluidos_los_tombstones(make_account):
    """Los tombstones también: al volver a entrar con el mismo Google se
    reciben los 3 créditos free y se puede probar el flujo gratis entero."""
    cuenta = make_account()
    _sembrar_cuenta_con_cartas_y_ledger(cuenta)
    SubTombstone.objects.create(sub_hash="abc", free_credits_consumed=3)

    call_command("purgar_produccion", "--si-estoy-seguro")

    for modelo in (
        Account, Chart, Interpretation, InterpretationSection,
        CreditTransaction, ProviderIdentity, SubTombstone, Session,
    ):
        assert modelo.objects.count() == 0
    # BirthData y Device no están en la lista del RF16, pero las dos quedan
    # huérfanas si no se nombran explícitamente (FK SET_NULL a Account):
    # BirthData contiene el mismo dato personal (nombre, fecha, coordenadas
    # de nacimiento) que `Chart`, y `api.deletion.delete_charts` ya la trata
    # como parte del borrado de una cuenta; Device sobreviviría con
    # account_id=NULL y su platform/push_token intactos. Dejarlas huérfanas
    # en la purga sería un olvido, no una decisión.
    assert BirthData.objects.count() == 0
    assert Device.objects.count() == 0


@pytest.mark.django_db
def test_no_toca_el_cms(make_account):
    """Las páginas de Wagtail y los datos de geonames no son historial de
    usuario: borrarlos dejaría el sitio sin contenido y sin buscador de lugares."""
    cuenta = make_account()
    _sembrar_cuenta_con_cartas_y_ledger(cuenta)
    SubTombstone.objects.create(sub_hash="def", free_credits_consumed=1)

    raiz = Page.objects.get(depth=1)
    raiz.add_child(instance=NoteIndexPage(title="Notas", slug="notas"))
    GeoName.objects.create(
        geonameid=3838583, name="Bariloche", asciiname="Bariloche",
        lat=-41.13, lng=-71.31, country_code="AR",
    )
    paginas_antes = Page.objects.count()
    geonames_antes = GeoName.objects.count()
    assert paginas_antes > 0
    assert geonames_antes > 0

    call_command("purgar_produccion", "--si-estoy-seguro")

    assert Account.objects.count() == 0  # la purga sí corrió
    assert Page.objects.count() == paginas_antes
    assert GeoName.objects.count() == geonames_antes
