# --- Builder: compila las deps que no traen wheel (pyswisseph necesita gcc) ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# build-essential (gcc + headers de libc, p.ej. math.h) sólo vive en el builder;
# pyswisseph se compila desde source. No llega a la imagen final.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps primero (capa cacheable mientras no cambie el lock), sin el código ni dev.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Código + instalar el proyecto.
COPY . .
RUN uv sync --frozen --no-dev

# --- Runtime: misma imagen base (mismo intérprete), sin compilador ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# `curl` es para el healthcheck y nada más. Coolify no chequea la aplicación
# desde afuera: ejecuta `curl` DENTRO del contenedor, y si no lo encuentra da el
# contenedor por enfermo y revierte el deploy al anterior. El 13-08-2026 eso
# hizo fallar dos deploys seguidos con "New container is not healthy, rolling
# back to the old container", sin que el sitio se cayera y sin ninguna pista en
# la interfaz.
# WeasyPrint (el PDF de la carta) no es Python puro: dibuja con Pango y
# gdk-pixbuf, y sin estas libs el import falla al arrancar, no al primer PDF.
#
# `fonts-dejavu-core` es el que dibuja los glifos astrológicos: Outfit y Space
# Mono son las tipografías de marca y van embebidas en el documento, pero no
# tienen ni ♈ ni ♃ ni ℞. En el spike del 16-08-2026 la carta salió bien porque
# DejaVu ya estaba en la imagen por arrastre de Pango; se instala explícito para
# que deje de depender de un accidente. Si desaparece, la carta entera sale en
# cajitas y no se entera nadie hasta abrir un PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 libffi8 \
       fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# El venv ya compilado + el código, tal cual quedaron en el builder.
COPY --from=builder /app /app

# Static del admin recolectado en build (WhiteNoise lo sirve). SECRET_KEY dummy:
# collectstatic corre con DEBUG off pero no necesita la key real. USE_DB_CACHE=1
# sólo satisface el fail-fast de `config/settings.py` (sin caché compartida no
# arranca fuera de DEBUG); collectstatic no toca cache ni DB, así que no hace
# falta ninguna base real acá. WAGTAILADMIN_BASE_URL y WEB_BASE_URL dummy por
# el mismo motivo: collectstatic no arma ninguna URL de imagen ni de enlace,
# sólo necesita que el import de settings no explote por el fail-fast de esas
# vars. Nada de esto queda en la imagen final: es un prefijo de ESTE `RUN`,
# no un `ENV`.
RUN SECRET_KEY=build-only-not-used USE_DB_CACHE=1 \
    WAGTAILADMIN_BASE_URL=http://build-only-not-used WEB_BASE_URL=http://build-only-not-used \
    python manage.py collectstatic --noinput

# Las imágenes del CMS viven fuera de /app: el deploy reemplaza ese directorio
# entero (`COPY --from=builder /app /app` de arriba). En Coolify hay que
# montar un volumen persistente en /data/media, o cada deploy las borra.
RUN mkdir -p /data/media
VOLUME ["/data/media"]

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
