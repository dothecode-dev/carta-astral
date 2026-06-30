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
# collectstatic corre con DEBUG off pero no necesita la key real.
RUN SECRET_KEY=build-only-not-used python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
