"""La mitad del embudo de pago que el navegador no puede medir.

Quien paga y cierra la pestaña no vuelve a ejecutar nada de la web —y el
informe tarda seis minutos, así que cerrar la pestaña es lo normal—. Si
`compra_completada` saliera del navegador, faltarían justo las compras que más
interesa contar. El webhook de Stripe es donde se sabe que la plata entró.

Lo que estos tests fijan, sobre todo: que medir no pueda romper el cobro. Esto
corre después de acreditar, y una excepción acá dejaría el webhook en 5xx, con
Stripe reintentando una compra ya aplicada.
"""

import httpx
import pytest

from api import analitica
from api.models import Account


@pytest.fixture
def cuenta(db):
    return Account.objects.create(email="alguien@example.com")


class RespuestaFalsa:
    status_code = 200

    def raise_for_status(self):
        return None


@pytest.fixture
def posthog(monkeypatch, settings):
    settings.POSTHOG_KEY = "phc_test"
    settings.POSTHOG_HOST = "https://us.i.posthog.com"
    enviados = []

    def post(url, **kwargs):
        enviados.append({"url": url, **kwargs})
        return RespuestaFalsa()

    monkeypatch.setattr(analitica.httpx, "post", post)
    return enviados


def test_el_evento_dice_de_qué_entorno_viene(cuenta, posthog, settings):
    """Sin esto, una compra de prueba del staging entra al mismo embudo que las
    reales: con la tarjeta 4242 se pueden inventar diez ventas en un minuto, y
    la tasa de conversión —el número que decide si conviene pagar tráfico—
    quedaría inflada sin que nadie lo note. El staging es espejo de producción,
    credenciales incluidas, así que la separación tiene que estar en el dato."""
    settings.ENTORNO = "staging"

    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert posthog[0]["json"]["properties"]["entorno"] == "staging"


def test_por_defecto_el_entorno_es_produccion(cuenta, posthog, settings):
    settings.ENTORNO = "produccion"

    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert posthog[0]["json"]["properties"]["entorno"] == "produccion"


def test_manda_el_evento_con_sus_propiedades(cuenta, posthog):
    analitica.evento(
        cuenta, "compra_completada",
        {"producto": "pack_3_natal", "monto_centavos": 7900, "moneda": "usd", "locale": "es"},
    )

    assert len(posthog) == 1
    cuerpo = posthog[0]["json"]
    assert cuerpo["event"] == "compra_completada"
    assert cuerpo["api_key"] == "phc_test"
    assert cuerpo["properties"]["producto"] == "pack_3_natal"
    assert cuerpo["properties"]["monto_centavos"] == 7900


def test_el_distinct_id_es_el_mismo_que_usa_la_web(cuenta, posthog):
    """`identificar()` de la web hace `posthog.identify(String(accountId))`.

    Si acá se mandara otra cosa —el mail, un uuid propio—, la compra quedaría
    colgada de una persona distinta de la que navegó, y el embudo no cerraría
    nunca: se vería tráfico sin compras y compras sin origen."""
    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert posthog[0]["json"]["distinct_id"] == str(cuenta.id)


def test_sin_key_no_sale_nada(cuenta, monkeypatch, settings):
    settings.POSTHOG_KEY = ""
    llamado = []
    monkeypatch.setattr(analitica.httpx, "post", lambda *a, **k: llamado.append(1))

    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert llamado == []


def test_el_mail_no_viaja(cuenta, posthog):
    """La política promete que el mail no sale del servidor. El id interno
    identifica a la persona para el embudo sin decir quién es."""
    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert cuenta.email not in str(posthog[0]["json"])


# --- Lo que no puede pasar -------------------------------------------------


def test_posthog_caido_no_propaga(cuenta, monkeypatch, settings, caplog):
    settings.POSTHOG_KEY = "phc_test"

    def post(url, **kwargs):
        raise httpx.ConnectTimeout("sin red")

    monkeypatch.setattr(analitica.httpx, "post", post)

    # Sin excepción: si subiera, el webhook devolvería 5xx y Stripe reintentaría
    # una compra ya acreditada.
    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert "no se pudo medir" in caplog.text


def test_un_error_http_tampoco_propaga(cuenta, monkeypatch, settings, caplog):
    settings.POSTHOG_KEY = "phc_test"

    class Rota:
        status_code = 400

        def raise_for_status(self):
            raise httpx.HTTPStatusError("400", request=None, response=None)  # type: ignore[arg-type]

    monkeypatch.setattr(analitica.httpx, "post", lambda *a, **k: Rota())

    analitica.evento(cuenta, "compra_completada", {"producto": "informe_natal"})

    assert "no se pudo medir" in caplog.text


def test_un_evento_fuera_de_la_lista_es_un_error_de_programacion(cuenta, posthog):
    """Misma razón que la lista cerrada de la web (`lib/telemetry/events.ts`):
    con nombres libres, en tres meses hay tres eventos midiendo lo mismo y
    ningún embudo cierra."""
    with pytest.raises(ValueError):
        analitica.evento(cuenta, "compra_hecha", {})
