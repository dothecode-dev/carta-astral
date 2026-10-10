"""Tipos de vínculo y roles por persona (RF13). Listas cerradas: el tipo y
los roles entran al prompt, y lo que entra al prompt no puede ser texto libre.

Los roles se guardan como claves; las etiquetas en cada idioma viven en
`interpret/vinculo.py`, que es quien las escribe en el prompt."""

TIPOS: tuple[str, ...] = ("pareja", "trabajo", "familia", "amistad")

ROLES: dict[str, tuple[str, ...]] = {
    "pareja": (),
    "amistad": (),
    "trabajo": ("jefe", "equipo", "socio", "colega"),
    "familia": ("progenitor", "hijo", "hermano", "otro_familiar"),
}

# Decisión de Gustavo del 10-10-2026. Pares sin orden: el rol es por persona.
_COMBINACIONES: dict[str, set[frozenset[str]]] = {
    "trabajo": {frozenset({"jefe", "equipo"}), frozenset({"socio"}), frozenset({"colega"})},
    "familia": {
        frozenset({"progenitor", "hijo"}), frozenset({"hermano"}), frozenset({"otro_familiar"}),
    },
}


class VinculoInvalido(ValueError):
    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def validar(tipo: str, rol_a: str, rol_b: str) -> tuple[str, str]:
    if tipo not in TIPOS:
        raise VinculoInvalido("tipo_invalido")
    permitidos = ROLES[tipo]
    if not permitidos:
        if rol_a or rol_b:
            raise VinculoInvalido("rol_invalido")
        return "", ""
    if rol_a not in permitidos or rol_b not in permitidos:
        raise VinculoInvalido("rol_invalido")
    if frozenset({rol_a, rol_b}) not in _COMBINACIONES[tipo]:
        raise VinculoInvalido("combinacion_invalida")
    return rol_a, rol_b
