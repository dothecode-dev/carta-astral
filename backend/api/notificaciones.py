"""Avisos al usuario. Hoy sólo dejan registro; la pantalla los muestra leyendo
el estado de la base. Cuando exista el proveedor de mail, se implementa `_enviar`
y los llamadores no cambian.

Nunca propaga una excepción: el aviso es lo último que pasa después de mover
plata, y un fallo acá no puede revertir la devolución de un crédito.
"""

import logging

logger = logging.getLogger(__name__)

EVENTOS = ("informe_no_entregado", "compra_acreditada")


def notificar(account, evento: str, contexto: dict, lang: str) -> None:
    if evento not in EVENTOS:
        raise ValueError(f"evento desconocido: {evento!r}")
    try:
        _enviar(account, evento, contexto, lang)
    except Exception:
        logger.exception("fallo el aviso %s a la cuenta %s", evento, account.pk)


def _enviar(account, evento, contexto, lang):
    logger.info(
        "aviso al usuario", extra={"evento": evento, "account": account.pk, "lang": lang},
    )
