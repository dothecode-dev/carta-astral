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
    Producto("informe_natal", 2900, CONSUMIBLE, ("leer_informe",), (("informe_natal", 1),)),
    Producto("pack_5_natal", 14990, CONSUMIBLE, ("leer_informe",), (("informe_natal", 5),)),
)

CATALOGO: dict[str, Producto] = {p.codigo: p for p in _PRODUCTOS}


def producto(codigo: str) -> Producto:
    try:
        return CATALOGO[codigo]
    except KeyError:
        raise KeyError(f"producto desconocido: {codigo}") from None


def productos_con_capacidad(capacidad: str) -> tuple[Producto, ...]:
    return tuple(p for p in CATALOGO.values() if capacidad in p.capacidades)


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
