"""Catálogo de productos: qué se vende, a cuánto, y qué habilita.

Es código y no una tabla a propósito: los precios no los edita nadie desde una
UI, y en código quedan versionados y revisables en el diff. Un producto declara
CAPACIDADES, no features sueltas: las vistas canjean por capacidad
(`canje.canjear(cuenta, "leer_informe", carta)`) y dejan que `SinDerecho` frene
al que no tiene con qué —no hay un chequeo previo separado del cobro—, así un
plan nuevo es una línea acá y no una recorrida por todas las vistas.
"""

from dataclasses import dataclass

CONSUMIBLE = "consumible"
ACCESO = "acceso"


@dataclass(frozen=True)
class Producto:
    codigo: str
    precio_centavos: int
    naturaleza: str
    capacidades: tuple[str, ...]
    #: Qué derechos deja al comprarlo: una o más `(código de producto, cantidad)`.
    #: Más de uno es un COMBO —"carta + horóscopo"—; uno solo con cantidad > 1 es
    #: un pack. Que sea una tupla de tuplas es lo que permite que agregar un
    #: combo sea una línea acá y nada más.
    otorga: tuple[tuple[str, int], ...]
    duracion_dias: int | None = None
    #: Si se ofrece. Un producto retirado sigue acá porque el historial lo
    #: nombra —`Movimiento`, `PasarelaCheckout`, un reembolso de una compra
    #: vieja lo busca en el catálogo—, pero no se puede abrir una compra nueva.
    vendible: bool = True
    #: Nombre del setting que lo enciende; "" = siempre encendido (RF19).
    flag: str = ""
    #: A qué sujeto se aplican sus capacidades: un derecho de un producto no
    #: canjea el sujeto de otro (RF18).
    sujeto: str = "natal"

    def __post_init__(self) -> None:
        if self.naturaleza not in (CONSUMIBLE, ACCESO):
            raise ValueError(f"naturaleza desconocida: {self.naturaleza!r}")
        if not self.capacidades:
            raise ValueError(f"{self.codigo} no declara capacidades")
        if self.naturaleza == ACCESO and self.duracion_dias is None:
            raise ValueError(f"{self.codigo} es de acceso y no declara duracion_dias")
        if not self.otorga:
            raise ValueError(f"{self.codigo} no otorga nada")


_PRODUCTOS = (
    Producto("lectura_breve", 0, CONSUMIBLE, ("leer_breve",), (("lectura_breve", 1),)),
    Producto("informe_natal", 500, CONSUMIBLE, ("leer_informe",), (("informe_natal", 1),)),
    # Retirados el 04-10-2026, cuando el informe pasó de US$ 29 a US$ 5: a ese
    # precio un pack ahorra centavos y sólo complica la elección. Quedan con
    # su precio de entonces porque hay compras y reembolsos que los nombran.
    Producto(
        "pack_3_natal", 7900, CONSUMIBLE, ("leer_informe",), (("informe_natal", 3),),
        vendible=False,
    ),
    Producto(
        "pack_5_natal", 12500, CONSUMIBLE, ("leer_informe",), (("informe_natal", 5),),
        vendible=False,
    ),
    # Precio provisorio (decisión del 10-10-2026); el definitivo se fija al lanzar.
    Producto(
        "informe_vinculo", 900, CONSUMIBLE, ("leer_vinculo",), (("informe_vinculo", 1),),
        flag="VINCULO_ENABLED", sujeto="vinculo",
    ),
)

CATALOGO: dict[str, Producto] = {p.codigo: p for p in _PRODUCTOS}


def producto(codigo: str) -> Producto:
    try:
        return CATALOGO[codigo]
    except KeyError:
        raise KeyError(f"producto desconocido: {codigo}") from None


def _encendido(p: Producto) -> bool:
    from django.conf import settings

    return not p.flag or bool(getattr(settings, p.flag))


def a_la_venta() -> list[Producto]:
    """Lo que se cobra hoy: con precio, no retirado y con su flag encendido
    (RF19). Es la única definición; el catálogo público, los cupones, el admin
    y la verificación contra Stripe preguntan acá."""
    return [
        p for p in CATALOGO.values() if p.precio_centavos > 0 and p.vendible and _encendido(p)
    ]


def disponible(codigo: str) -> bool:
    """Si se puede abrir una compra de este producto: existe, no está retirado
    y su flag está encendido."""
    p = CATALOGO.get(codigo)
    return p is not None and p.vendible and _encendido(p)


def productos_con_capacidad(capacidad: str) -> tuple[Producto, ...]:
    return tuple(p for p in CATALOGO.values() if capacidad in p.capacidades)


def sujeto_de(capacidad: str) -> str:
    """Sobre qué sujeto se ejerce una capacidad. Todos los productos que la
    declaran coinciden; si no, el catálogo está mal y conviene que explote."""
    (sujeto,) = {p.sujeto for p in productos_con_capacidad(capacidad)}
    return sujeto


def codigos_otorgados_por(capacidad: str) -> set[str]:
    """En qué `Derecho` puede vivir esa capacidad.

    No es lo mismo que los productos que la declaran: un pack se compra como
    `pack_5_natal` pero deja un derecho de `informe_natal`, y un combo deja uno
    por cada cosa que otorga. Quien busca "¿con qué puede leer un informe?"
    pregunta por esto.
    """
    return {
        codigo
        for prod in productos_con_capacidad(capacidad)
        for codigo, _ in prod.otorga
    }
