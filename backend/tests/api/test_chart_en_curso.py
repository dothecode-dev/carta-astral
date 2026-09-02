"""El detalle de la carta dice qué se está escribiendo ahora mismo.

Sin esto, alguien que pide su informe, cierra la pestaña y vuelve más tarde se
encuentra la carta ofreciéndole generar de nuevo lo que ya pagó y se está
escribiendo: `_chart_repr` sólo listaba las interpretaciones `completa=True`, así
que "no tiene" y "se está generando" eran el mismo payload. La memoria de "yo
pedí esto" vivía sólo en el `sessionStorage` del navegador, que sobrevive un F5
pero muere al cerrar la pestaña.

Qué decide: que el informe se vaya a terminar, no que haya un proceso
escribiéndolo en este segundo. Antes lo decidía el lock —vivo, alguien
escribe; vencido, se cayó y vuelven los botones— porque el único que podía
reintentar era el usuario apretando de nuevo. Desde `reanudar_informes` eso ya
no es cierto: un cron retoma lo caído mientras queden intentos, así que un lock
vencido es una pausa, no un final, y mostrar el bloque de venta ahí es
ofrecerle comprar de nuevo lo que ya pagó (pasó en producción el 01-09-2026).

La espera eterna la sigue acotando `INTENTOS_MAXIMOS`: agotados los tres sin
completar, la política de RF21 devuelve el derecho y borra la fila — ahí sí
corresponde volver a mostrar los botones, y con el derecho de nuevo en la
cuenta.
"""

import pytest
from django.core.cache import cache

from api.interpretation_service import INTENTOS_MAXIMOS, PROMPT_VERSION, _lock_key
from api.models import Interpretation

pytestmark = pytest.mark.django_db


def _pedir(client, chart):
    return client.get(f"/api/charts/{chart.uuid}/").json()


def _en_curso(chart, tier="largo", lang="es"):
    """Deja la carta como la deja `iniciar_generacion`: fila incompleta + lock."""
    interp = Interpretation.objects.create(
        chart=chart, lang=lang, tier=tier, prompt_version=PROMPT_VERSION, completa=False,
    )
    cache.set(_lock_key(chart, tier), "un-token", timeout=600)
    return interp


def test_una_carta_sin_nada_no_declara_nada_en_curso(client_autenticado, chart):
    assert _pedir(client_autenticado, chart)["en_curso"] == {}


def test_una_generacion_viva_aparece_en_curso(client_autenticado, chart):
    _en_curso(chart, tier="largo")

    assert _pedir(client_autenticado, chart)["en_curso"] == {"es": ["largo"]}


def test_una_generacion_caida_sigue_pendiente_porque_el_cron_la_retoma(
    client_autenticado, chart,
):
    """El intento murió a mitad y nadie está escribiendo ahora mismo, pero
    quedan intentos: `reanudar_informes` la va a retomar.

    Si esto no contara, la carta le ofrecería al usuario comprar por US$ 29 un
    informe que ya pagó y que se está por terminar solo.
    """
    _en_curso(chart, tier="largo")
    cache.delete(_lock_key(chart, "largo"))

    assert _pedir(client_autenticado, chart)["en_curso"] == {"es": ["largo"]}


def test_una_generacion_que_agoto_los_intentos_ya_no_esta_pendiente(
    client_autenticado, chart,
):
    """Agotados los tres intentos ya no hay nada que esperar: RF21 devuelve el
    derecho y borra la fila. Seguir mostrando la espera sería esperar para
    siempre por un informe que nadie va a terminar."""
    interp = _en_curso(chart, tier="largo")
    cache.delete(_lock_key(chart, "largo"))
    Interpretation.objects.filter(pk=interp.pk).update(intentos=INTENTOS_MAXIMOS)

    assert _pedir(client_autenticado, chart)["en_curso"] == {}


def test_una_interpretacion_terminada_no_esta_en_curso(client_autenticado, chart):
    Interpretation.objects.create(
        chart=chart, lang="es", tier="corto", prompt_version=PROMPT_VERSION,
        completa=True, text="ya está",
    )

    datos = _pedir(client_autenticado, chart)
    assert datos["en_curso"] == {}
    assert datos["interpretations"] == {"es": ["corto"]}


def test_los_dos_productos_pueden_estar_en_curso_a_la_vez(client_autenticado, chart):
    """La breve y el completo son dos filas con su propio lock (RF9)."""
    _en_curso(chart, tier="corto")
    _en_curso(chart, tier="largo")

    assert _pedir(client_autenticado, chart)["en_curso"] == {"es": ["corto", "largo"]}


def test_una_version_de_prompt_vieja_no_cuenta(client_autenticado, chart):
    """Mismo criterio que `interpretations`: sólo la versión vigente."""
    Interpretation.objects.create(
        chart=chart, lang="es", tier="largo", prompt_version="prompt-viejo", completa=False,
    )
    cache.set(_lock_key(chart, "largo"), "un-token", timeout=600)

    assert _pedir(client_autenticado, chart)["en_curso"] == {}


def test_el_listado_dice_lo_mismo_que_el_detalle(client_autenticado, chart):
    """El contrato de la API pide que listado y detalle no diverjan: cuando lo
    hicieron, la app rompió al navegar entre uno y otro (pasó con
    `interpretation_langs`). El costo es nulo para una carta sin nada a medio
    escribir: el cache sólo se consulta si hay una fila incompleta."""
    _en_curso(chart, tier="largo")

    detalle = _pedir(client_autenticado, chart)["en_curso"]
    listado = client_autenticado.get("/api/charts/").json()["results"][0]["en_curso"]
    assert detalle == listado == {"es": ["largo"]}
