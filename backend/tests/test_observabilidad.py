"""Un fallo del hilo de generación tiene que dejar rastro en algún lado.

El código del informe dice, en tres lugares distintos, que nunca deja una
excepción sin loguear: "si el hilo de fondo muere en silencio, el informe queda
colgado con el crédito ya cobrado y nadie se entera hasta que el usuario se
queja". Era mentira por omisión: `config/settings.py` no configuraba `LOGGING`,
así que los loggers de `api` e `interpret` propagaban a un root sin handlers y
sólo lo de nivel ERROR salía, por el handler de último recurso de la stdlib.

Se pagó el 01-09-2026: la interpretación 8 se cortó en la sección 3 y no quedó
ni una línea sobre por qué. Los logs del contenedor viejo se fueron con él y no
había Sentry en el backend (el que estaba cableado es el de la web).
"""

import logging

from django.conf import settings


def test_los_logs_de_api_e_interpret_salen_por_consola():
    """Sin un handler de consola, `logger.exception` del hilo de fondo va a la
    nada: no aparece en `docker logs` y no hay forma de saber qué falló."""
    for nombre in ("api", "interpret"):
        config = settings.LOGGING["loggers"][nombre]
        assert "console" in config["handlers"]


def test_el_nivel_de_api_e_interpret_deja_pasar_el_info():
    """`interpret.generator` loguea en INFO el `stop_reason` y los
    `output_tokens` de cada llamada, a propósito: es el dato con el que se
    decide si el techo de tokens quedó corto (ya pasó con la lectura breve).
    Con el nivel en WARNING ese dato no existe."""
    for nombre in ("api", "interpret"):
        assert settings.LOGGING["loggers"][nombre]["level"] == "INFO"


def test_el_handler_de_consola_escribe_a_stdout():
    handler = settings.LOGGING["handlers"]["console"]
    assert handler["class"] == "logging.StreamHandler"
    assert handler["stream"] == "ext://sys.stdout"


def test_la_config_declarada_es_la_que_esta_aplicada():
    """`settings.LOGGING` sólo sirve si Django la aplicó de verdad
    (`LOGGING_CONFIG` en su default). Sin esta comprobación, los tres tests de
    arriba pasarían igual con un diccionario decorativo que nadie carga."""
    handlers = logging.getLogger("api").handlers
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)


def test_sin_dsn_no_se_inicializa_sentry(monkeypatch):
    """El DSN es opcional: en desarrollo y en los tests no está, y el arranque
    no puede depender de él."""
    from config.observabilidad import init_sentry

    llamadas = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: llamadas.append(kw))

    init_sentry(dsn="", entorno="test", release=None)

    assert llamadas == []


def test_con_dsn_se_inicializa_sentry_sin_mandar_datos_personales(monkeypatch):
    """`send_default_pii` apagado: las cartas llevan nombre, fecha y lugar de
    nacimiento, y el repo es público bajo AGPL — un DSN filtrando datos de
    nacimiento a un tercero es exactamente lo que no puede pasar."""
    from config.observabilidad import init_sentry

    llamadas = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: llamadas.append(kw))

    init_sentry(dsn="https://clave@sentry.io/1", entorno="produccion", release="abc123")

    assert len(llamadas) == 1
    assert llamadas[0]["dsn"] == "https://clave@sentry.io/1"
    assert llamadas[0]["environment"] == "produccion"
    assert llamadas[0]["release"] == "abc123"
    assert llamadas[0]["send_default_pii"] is False
