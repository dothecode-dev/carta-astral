"""Botón de arrepentimiento (Res. SCI 424/2020): registra, avisa, no reembolsa.

Mini-spec en docs/2026-10-19-mini-spec-boton-arrepentimiento.md. El formulario
es público y cualquiera puede escribir el mail de otro, así que nada de acá
mueve plata (decisión de Gustavo, 19-10): se guarda la solicitud con un código,
el código vuelve en la respuesta (el «mismo medio» de la resolución) y por
mail, y el admin decide el reembolso desde la pasarela.
"""

import datetime as dt
import logging
import re
import secrets

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from api import compra_anonima, notificaciones
from api.avisos import avisar_admin
from api.models import PasarelaCheckout, SolicitudArrepentimiento

logger = logging.getLogger(__name__)

#: Sin 0/O ni 1/I: el código se dicta y se copia a mano.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_VENTANA = dt.timedelta(days=30)
_NUMERO = re.compile(r"[^A-Za-z0-9_]")


def _codigo() -> str:
    return "ARR-" + "".join(secrets.choice(_ALFABETO) for _ in range(8))


def _compras_recientes(email: str) -> list[PasarelaCheckout]:
    desde = timezone.now() - _VENTANA
    return list(
        PasarelaCheckout.objects.filter(acreditado_at__gte=desde)
        .filter(Q(account__email__iexact=email) | Q(mail_comprador__iexact=email))
        .order_by("-acreditado_at")[:10]
    )


def registrar(email: str, numero_compra: str, locale: str) -> SolicitudArrepentimiento:
    """Guarda la solicitud, manda el código por mail y avisa al admin. El
    mail que falla no deshace nada: la solicitud vale igual y el admin se
    entera de que tiene que responder por otro lado."""
    numero = _NUMERO.sub("", numero_compra or "")[:40]
    for _ in range(5):
        try:
            solicitud = SolicitudArrepentimiento.objects.create(
                codigo=_codigo(), email=email, numero_compra=numero, locale=locale,
            )
            break
        except IntegrityError:  # el código ya existía: otro
            logger.warning("código de arrepentimiento repetido, se genera otro")
    else:
        raise RuntimeError("no se pudo generar un código de arrepentimiento único")

    mail_ok = True
    try:
        notificaciones.enviar_arrepentimiento(email, solicitud.codigo, locale)
    except notificaciones.EnvioFallido:
        logger.exception("arrepentimiento %s: no salió el mail con el código", solicitud.codigo)
        mail_ok = False

    compras = _compras_recientes(email)
    lineas = [
        f"Botón de arrepentimiento {solicitud.codigo}: {compra_anonima.enmascarar(email)}"
        + (f", compra n.° {numero}" if numero else ", sin número de compra")
        + ". Responder y, si corresponde, reembolsar desde la pasarela.",
    ]
    if compras:
        lineas.append("Compras de ese mail en los últimos 30 días:")
        lineas += [
            f"· {c.checkout_id} · {c.moneda} · {timezone.localtime(c.acreditado_at):%d/%m/%Y}" for c in compras
        ]
    else:
        lineas.append("Ese mail no tiene compras acreditadas en los últimos 30 días.")
    if not mail_ok:
        lineas.append("OJO: el mail con el código no salió: responderle a mano.")
    avisar_admin("\n".join(lineas))
    return solicitud
