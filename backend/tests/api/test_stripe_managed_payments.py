"""Managed Payments va explícito en CADA sesión, y esto lo verifica.

Es el único punto de la migración a Stripe que falla en silencio y cuesta
plata. `managed_payments[enabled]=true` NO es obligatorio: viene activado por
defecto en la cuenta. Pero ese default es un switch del dashboard con un "Turn
off" al lado, y si alguien lo apaga —o si Stripe cambia el default— el cobro
pasa a ser Stripe normal: el IVA de más de 80 países vuelve a ser nuestro, el
merchant of record vuelve a ser la LLC, y el código no se entera. Sin error,
sin log, sin aviso: sólo una liquidación distinta a fin de mes.

Un recordatorio en la spec no alcanza. Por eso el test recorre el código del
cliente en vez de probar un camino: si mañana alguien agrega otra ruta que abra
una sesión —una suscripción, un pago único distinto—, este test la ve.
"""

import ast
import pathlib

CLIENTE = pathlib.Path(__file__).resolve().parents[2] / "api" / "stripe_client.py"


def _llamadas_a_crear_sesion(arbol: ast.Module) -> list[ast.Call]:
    """Todo `stripe.checkout.Session.create(...)` del archivo."""
    return [
        nodo for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "create"
        and ast.unparse(nodo.func).endswith("checkout.Session.create")
    ]


def test_toda_sesion_se_crea_con_managed_payments():
    arbol = ast.parse(CLIENTE.read_text())
    llamadas = _llamadas_a_crear_sesion(arbol)

    assert llamadas, "no se encontró ninguna creación de Checkout Session que verificar"
    for llamada in llamadas:
        flags = [k for k in llamada.keywords if k.arg == "managed_payments"]
        assert flags, (
            f"línea {llamada.lineno}: se crea una Checkout Session sin "
            "managed_payments. El IVA de 80 países vuelve a ser nuestro y "
            "nada lo avisa."
        )
        assert ast.literal_eval(flags[0].value) == {"enabled": True}, (
            f"línea {llamada.lineno}: managed_payments tiene que ir en "
            "{'enabled': True}"
        )
