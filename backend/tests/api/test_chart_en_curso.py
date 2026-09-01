"""El detalle de la carta dice qué se está escribiendo ahora mismo.

Sin esto, alguien que pide su informe, cierra la pestaña y vuelve más tarde se
encuentra la carta ofreciéndole generar de nuevo lo que ya pagó y se está
escribiendo: `_chart_repr` sólo listaba las interpretaciones `completa=True`, así
que "no tiene" y "se está generando" eran el mismo payload. La memoria de "yo
pedí esto" vivía sólo en el `sessionStorage` del navegador, que sobrevive un F5
pero muere al cerrar la pestaña.

El matiz que evita la espera eterna: una fila incompleta NO alcanza para decir
"en curso". Si el proceso murió a mitad (un deploy, por ejemplo), esa fila queda
`completa=False` para siempre y la pantalla esperaría sin fin. Lo que decide es
el lock de generación: vivo significa que hay alguien escribiendo; vencido, que
se cayó — y ahí corresponde volver a mostrar los botones, para que el reintento
consuma un intento y, al tercero, devuelva el crédito.
"""

import pytest
from django.core.cache import cache

from api.interpretation_service import PROMPT_VERSION, _lock_key
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


def test_una_generacion_cuyo_lock_vencio_no_cuenta_como_en_curso(client_autenticado, chart):
    """El proceso murió a mitad: la fila queda, pero nadie la está escribiendo.

    Si esto contara como "en curso", la pantalla esperaría para siempre por un
    informe que nadie va a terminar.
    """
    _en_curso(chart, tier="largo")
    cache.delete(_lock_key(chart, "largo"))

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
