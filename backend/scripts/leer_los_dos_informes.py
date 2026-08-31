"""Genera una lectura breve y un informe completo REALES y los escribe a disco,
para leerlos antes de decidir si `claude-sonnet-5` se queda.

Gasta plata de verdad: la breve es una llamada al modelo (~1,6¢) y el informe
completo son ocho (~18¢). Corre contra la base local, nunca contra producción.

    cd backend && set -a && . ./.env && set +a && \
        DEBUG=1 .venv/bin/python scripts/leer_los_dos_informes.py

Django NO carga `.env` solo (no hay dotenv en el proyecto): lo sourcea el
Makefile. Sin el `set -a && . ./.env` la key no llega y el script aborta.

Deja `/tmp/astra-breve.md` y `/tmp/astra-completo.md`.
"""
import os
import sys
from pathlib import Path

import django

# Al correr `python scripts/leer_los_dos_informes.py`, Python sólo agrega
# `scripts/` a sys.path, no `backend/`: sin esto, `config.settings` no se
# encuentra. Mismo motivo que en `medir_pdf.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from api import interpretation_service as svc  # noqa: E402
from api.chart_service import create_chart  # noqa: E402
from api.canje import otorgar  # noqa: E402
from api.models import Account  # noqa: E402

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(
        "Falta ANTHROPIC_API_KEY en el entorno. Está en backend/.env, pero Django no\n"
        "lo carga solo. Corré:  set -a && . ./.env && set +a && DEBUG=1 .venv/bin/python "
        "scripts/leer_los_dos_informes.py"
    )

# La carta golden: 14-07-1989, 23:45, Buenos Aires — la misma con la que se
# validó el motor de cálculo, así que el texto se puede comparar con lo que ya
# conocés del producto viejo. Se arma por el mismo camino que la app (que
# resuelve zona horaria y serializa igual), no a mano.
cuenta = Account.objects.create()
# Una lectura breve y un informe completo: los dos derechos que el script
# canjea abajo. Sin esto `iniciar_generacion` levanta `SinDerecho` — desde
# el modelo de canje una cuenta recién creada no puede canjear nada.
otorgar(cuenta, "lectura_breve", 1, origen="regalo", external_id=f"script:leer:{cuenta.pk}:breve")
otorgar(cuenta, "informe_natal", 1, origen="compra", external_id=f"script:leer:{cuenta.pk}:informe")
chart = create_chart({
    "name": "Lectura de control",
    "date": "1989-07-14",
    "time": "23:45",
    "time_known": True,
    "lat": -34.6037,
    "lng": -58.3816,
    "place_label": "Buenos Aires",
}, cuenta)

for tier, salida in (("corto", "/tmp/astra-breve.md"), ("largo", "/tmp/astra-completo.md")):
    print(f"generando {tier}… (el completo son ocho llamadas, tarda varios minutos)")
    interp = svc.iniciar_generacion(chart, "es", cuenta, tier=tier)
    svc.completar_generacion(interp, chart, cuenta)
    interp.refresh_from_db()
    if not interp.completa:
        print(f"  ¡el {tier} no se completó! revisá los logs de arriba")
        continue
    texto = "\n\n".join(f"## {s.slug}\n\n{s.texto}" for s in interp.secciones.all())
    Path(salida).write_text(texto)
    print(f"  {len(texto.split())} palabras → {salida}")
