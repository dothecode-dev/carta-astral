"""Cuánto tarda y cuánta memoria usa el PDF del informe completo.

El VPS tiene 1,7 GB libres y ya usa swap en reposo: un PDF que consuma 500 MB
mientras corre un deploy puede tumbar producción.

`pdf_payload.build()` sólo arma la lectura (título y texto de cada sección):
la geometría de la rueda y las tablas de posiciones/aspectos las calcula el
cliente (`astra-wheel`) y no vive en la base. Acá se arma una mínima pero
completa —lo que se quiere medir es el costo de renderizar ocho secciones de
verdad, no el de dibujar la rueda, que ya se mide aparte.
"""
import os
import resource
import sys
import time
from pathlib import Path

import django

# Al correr `python scripts/medir_pdf.py`, Python sólo agrega `scripts/` a
# sys.path, no `backend/`: sin esto, `config.settings` no se encuentra.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from api.chart_pdf_service import render_pdf  # noqa: E402
from api.models import Interpretation  # noqa: E402
from api.pdf_payload import ChartPdfSerializer  # noqa: E402


def _mb_rss() -> float:
    # `ru_maxrss` viene en KB en Linux (el VPS real) y en bytes en macOS: sin
    # este ajuste el número sale 1024 veces más chico en desarrollo.
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / 1024 / 1024 if sys.platform == "darwin" else raw / 1024


# Antes de renderizar nada: cuánto pesa ya el proceso por Django + DRF +
# weasyprint (que import perezoso hace que recién cargue acá, en el primer
# render_pdf de este proceso). En producción esa carga la paga el worker una
# sola vez al arrancar, no cada request; lo que importa para el techo del
# VPS es el incremento de abajo, no este número.
mb_antes = _mb_rss()

interp = Interpretation.objects.filter(completa=True).first()
assert interp is not None, "generá un informe completo antes de medir"

payload = {
    "labels": {
        "brand_tagline": "Tu carta natal", "eyebrow": "Carta natal",
        "chart_name": interp.chart.birth_data.name or "Carta",
        "birth_line": "12 de marzo de 1994 · 07:20 · Buenos Aires, Argentina",
        "positions": "Posiciones", "aspects": "Aspectos",
        "reading": "Tu lectura", "made_with": "Hecho con ASTRA",
    },
    "positions": [
        {"glyph": "☉", "name": "Sol", "position": "♓ Piscis 21°36′",
         "house": "XII", "retrograde": False},
    ],
    "aspects": [{"glyph": "☉ △ ♃", "name": "Trígono", "detail": "orbe 7.2°"}],
    "wheel": None,
    "aspect_matrix": None,
    "reading_lang": interp.lang,
}

ser = ChartPdfSerializer(data=payload)
assert ser.is_valid(), ser.errors

t0 = time.time()
blob = render_pdf(interp.chart, ser.validated_data)
segundos = time.time() - t0
mb_despues = _mb_rss()

print(f"segundos: {segundos:.2f}")
print(f"KB del PDF: {len(blob) / 1024:.0f}")
print(f"MB de RSS antes de renderizar (Django + weasyprint ya cargados): {mb_antes:.0f}")
print(f"MB de RSS máximo tras renderizar: {mb_despues:.0f}")
print(f"MB que sumó este render puntual: {mb_despues - mb_antes:.0f}")
