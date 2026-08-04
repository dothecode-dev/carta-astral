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

# El venv ya compilado + el código, tal cual quedaron en el builder.
COPY --from=builder /app /app

# Static del admin recolectado en build (WhiteNoise lo sirve). SECRET_KEY dummy:
# collectstatic corre con DEBUG off pero no necesita la key real. USE_DB_CACHE=1
# sólo satisface el fail-fast de `config/settings.py` (sin caché compartida no
# arranca fuera de DEBUG); collectstatic no toca cache ni DB, así que no hace
# falta ninguna base real acá. WAGTAILADMIN_BASE_URL dummy por el mismo motivo:
# collectstatic no arma ninguna URL de imagen, sólo necesita que el import de
# settings no explote por el fail-fast de esa var. Nada de esto queda en la
# imagen final: es un prefijo de ESTE `RUN`, no un `ENV`.
RUN SECRET_KEY=build-only-not-used USE_DB_CACHE=1 WAGTAILADMIN_BASE_URL=http://build-only-not-used \
    python manage.py collectstatic --noinput

# Las imágenes del CMS viven fuera de /app: el deploy reemplaza ese directorio
# entero (`COPY --from=builder /app /app` de arriba). En Coolify hay que
# montar un volumen persistente en /data/media, o cada deploy las borra.
RUN mkdir -p /data/media
VOLUME ["/data/media"]

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
