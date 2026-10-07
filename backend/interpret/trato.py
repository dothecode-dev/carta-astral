"""Cómo quiere la persona que le hablen (spec docs/2026-10-07-spec-trato-lector.md).

Vive en `interpret/` porque la instrucción al modelo sale de acá; `api` lo
importa para validar. Vacío = no eligió, y se trata igual que "neutro".
"""

TRATOS = ("femenino", "masculino", "neutro")
