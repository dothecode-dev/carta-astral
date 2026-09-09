"""Lo que el backend le manda a Sentry no puede llevar el cuerpo del request.

`send_default_pii=False` NO alcanza, y creer que sí es lo que dejó este agujero
abierto: esa opción gobierna cookies y datos del usuario, mientras que el cuerpo
del pedido lo gobierna `max_request_body_size`, que por defecto viene en
`"medium"` —o sea, se manda—. La integración de Django cuelga un procesador del
request entero, así que **cualquier** evento capturado durante ese pedido
—incluido un simple `logger.error`, no hace falta una excepción— sale con el
cuerpo adjunto.

Por dónde duele: `POST /api/auth/email` recibe `{email, codigo}`, y ese código
de seis dígitos es una credencial de un solo uso que abre la cuenta. `POST
/api/charts` recibe nombre, fecha, hora y lugar de nacimiento. El docstring de
`config/observabilidad.py` ya decía que mandarle eso a un tercero «es justo lo
que no puede pasar»: la intención estaba escrita, la configuración no la
cumplía.

El test de configuración de `test_observabilidad.py` no podía verlo —afirma
sobre los kwargs, y el kwarg que faltaba no estaba— y el del webhook tampoco,
porque mira `caplog`, que es el registro local: en los tests Sentry nunca
arranca (no hay DSN) y ese canal queda sin ejercitar. Este test arranca el
cliente de verdad, con la misma configuración de producción, y mira lo que
saldría por el cable.
"""

import json

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from config.observabilidad import init_sentry

CORREO = "una-persona@ejemplo.com"
CODIGO = "482913"


class TransporteQueGuarda(Transport):
    """Se queda con los sobres en memoria en vez de mandarlos a Sentry."""

    def __init__(self) -> None:
        super().__init__()
        self.sobres: list = []

    def capture_envelope(self, envelope) -> None:  # type: ignore[no-untyped-def]
        self.sobres.append(envelope)

    def texto(self) -> str:
        """Todo lo que saldría por el cable, aplanado, para poder buscar dentro.

        Se serializa el sobre entero y no sólo `event["request"]["data"]`: lo
        que importa no es por qué campo viaja el dato, sino que no viaje por
        ninguno.
        """
        partes = []
        for sobre in self.sobres:
            for item in sobre.items:
                partes.append(json.dumps(item.payload.json, default=str))
        return "\n".join(partes)


@pytest.fixture
def sentry_capturado(monkeypatch):
    """Sentry arrancado con la configuración REAL de producción.

    Los kwargs salen de `init_sentry`, no de una copia escrita a mano acá: si
    mañana alguien le cambia una opción a la función, este test la usa. Lo único
    que se agrega es el transporte de prueba.
    """
    kwargs: list[dict] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: kwargs.append(kw))
    init_sentry(dsn="https://clave@sentry.io/1", entorno="test", release=None)
    monkeypatch.undo()

    assert len(kwargs) == 1, "init_sentry dejó de inicializar: el test no prueba nada"
    transporte = TransporteQueGuarda()
    sentry_sdk.init(**kwargs[0], transport=transporte)
    try:
        yield transporte
    finally:
        # Sin esto el cliente queda vivo para el resto de la suite.
        sentry_sdk.get_client().close()
        sentry_sdk.init(dsn="")


def test_un_evento_disparado_durante_un_pedido_no_lleva_el_cuerpo(client, sentry_capturado):
    """El canal es el mismo para todos los endpoints: el procesador que adjunta
    el cuerpo lo instala la integración de Django por request, no la vista.

    Se usa el webhook de Resend porque loguea en ERROR de forma garantizada
    cuando falta su secreto (fail-closed) y no necesita base de datos. El cuerpo
    lleva un correo y un código porque son los dos datos que de verdad viajan en
    `POST /api/auth/email`.
    """
    client.post(
        "/api/webhooks/resend/",
        {"type": "email.bounced", "email": CORREO, "codigo": CODIGO},
        content_type="application/json",
    )
    sentry_sdk.flush()

    salida = sentry_capturado.texto()
    assert salida, "no se capturó ningún evento: el test no probó nada"
    assert CORREO not in salida
    assert CODIGO not in salida


def test_la_configuracion_declara_que_el_cuerpo_no_se_manda(monkeypatch):
    """El de arriba prueba el efecto; éste ancla la causa, para que el día que
    falle se sepa qué opción mirar."""
    kwargs: list[dict] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: kwargs.append(kw))

    init_sentry(dsn="https://clave@sentry.io/1", entorno="produccion", release=None)

    assert kwargs[0]["max_request_body_size"] == "never"
