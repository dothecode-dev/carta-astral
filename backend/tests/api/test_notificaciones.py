"""Notificaciones al usuario: interfaz estable para avisos de eventos críticos.

Protege que los avisos nunca rompan el flujo de negocio (plata, créditos).
"""

import pytest

from api import notificaciones


def _que_revienta(*args, **kwargs):
    raise RuntimeError("fallo simulado del backend de notificaciones")


@pytest.mark.django_db
def test_notificar_deja_registro_estructurado(caplog, make_account):
    """El aviso queda registrado en el log estructurado con evento y contexto."""
    acc = make_account()
    with caplog.at_level("INFO", logger="api.notificaciones"):
        notificaciones.notificar(acc, "informe_no_entregado", {"chart": "abc"}, lang="es")
    assert any(getattr(r, "evento", None) == "informe_no_entregado" for r in caplog.records)


@pytest.mark.django_db
def test_notificar_no_revienta_si_el_backend_falla(monkeypatch, make_account):
    """Un aviso que falla nunca puede tumbar la devolución del crédito: la
    plata importa más que el mail.
    """
    monkeypatch.setattr(notificaciones, "_enviar", _que_revienta)
    notificaciones.notificar(make_account(), "informe_no_entregado", {}, lang="es")


@pytest.mark.django_db
def test_notificar_rechaza_eventos_desconocidos(make_account):
    """Eventos desconocidos son error de programación y deben fallar."""
    with pytest.raises(ValueError, match="evento desconocido"):
        notificaciones.notificar(make_account(), "evento_inexistente", {}, lang="es")
