# Entorno de desarrollo de ASTRA: backend Django + web Next, juntos y en local.
#
# `make dev` levanta los dos. La web apunta al backend local por `web/.env.local`
# (ver `web/.env.example`), así que se desarrolla contra datos reales sin tocar
# producción ni depender de que el servidor esté arriba.
#
# Nada de esto cambia cómo se despliega: Coolify sigue construyendo con los
# Dockerfile de cada carpeta.

BACK_PORT ?= 8000
WEB_PORT  ?= 3000

# Cache en la base, como producción, sólo para el servidor de desarrollo. Con el
# cache en memoria del default, el lock que impide generar dos veces la misma
# lectura no existe entre procesos: el 02-08 eso hizo que un fallo de
# concurrencia sólo se pudiera reproducir contra el servidor de verdad. El
# throttle y el tope diario, igual.
#
# No va exportada al Makefile entero: pytest crea su propia base y ahí la tabla
# de cache no existe.
DEV_ENV = DEBUG=1 USE_DB_CACHE=1

.DEFAULT_GOAL := help
.PHONY: help dev back web stop install test test-back test-web sky \
        staging-up staging-down staging-logs staging-reset test-back-pg

help: ## Muestra estos comandos
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

dev: stop ## Levanta backend y web juntos (Ctrl-C corta los dos)
	@echo "  backend → http://localhost:$(BACK_PORT)"
	@echo "  web     → http://localhost:$(WEB_PORT)"
	@echo ""
	@trap 'kill 0' EXIT INT TERM; \
		(cd backend && set -a && [ -f .env ] && . ./.env; set +a; \
			$(DEV_ENV) .venv/bin/python manage.py migrate --noinput >/dev/null && \
			$(DEV_ENV) .venv/bin/python manage.py createcachetable >/dev/null && \
			$(DEV_ENV) .venv/bin/python manage.py runserver $(BACK_PORT)) & \
		(cd web && npm run dev -- --port $(WEB_PORT)) & \
		wait

back: ## Sólo el backend
	cd backend && set -a && [ -f .env ] && . ./.env; set +a; \
		$(DEV_ENV) .venv/bin/python manage.py createcachetable >/dev/null && \
		$(DEV_ENV) .venv/bin/python manage.py runserver $(BACK_PORT)

web: ## Sólo la web
	cd web && npm run dev -- --port $(WEB_PORT)

stop: ## Libera los puertos (mata lo que haya quedado colgado)
	@lsof -ti:$(BACK_PORT) | xargs kill -9 2>/dev/null || true
	@lsof -ti:$(WEB_PORT) | xargs kill -9 2>/dev/null || true

install: ## Instala las dependencias de los dos proyectos
	cd backend && uv sync
	# `npm ci`, no `npm install`: en macOS el segundo reescribe el lock sacando
	# las dependencias opcionales de Linux (@emnapi y compañía), que es lo que
	# arregló 1ea577f. Cada `make install` volvía a romper el build de CI y el
	# Dockerfile si el lock se commiteaba sin mirar. `ci` respeta el lock tal
	# cual y falla si no coincide con package.json, que es lo que queremos.
	cd web && npm ci
	@test -f web/.env.local || cp web/.env.example web/.env.local
	# `main` no está protegida y se pushea directo: el hook de pre-push es el
	# único gate antes de GitHub. `core.hooksPath` es config local de cada
	# clon, así que no viaja con el repo y hay que ponerla acá.
	@git config core.hooksPath .githooks
	@echo "listo — 'make dev' para levantar todo"

test: test-back test-web ## Corre todos los gates, los mismos que el CI

test-back: ## Gates del backend: pytest, ruff, contratos, tipos, migraciones
	cd backend && DEBUG=1 .venv/bin/python -m pytest -q
	cd backend && .venv/bin/ruff check .
	cd backend && .venv/bin/lint-imports
	cd backend && .venv/bin/mypy
	# Si alguien cambia un modelo y no genera la migración, el deploy se rompe
	# al arrancar. Mejor que se rompa acá. Es el gate del CI que faltaba.
	cd backend && DEBUG=1 .venv/bin/python manage.py makemigrations --check --dry-run

test-web: ## Gates de la web: eslint, tests, tipos, legales, los dos builds
	cd web && npx eslint .
	cd web && npm test
	cd web && npx tsc --noEmit
	cd web && npm run check:legal
	cd web && npm run build
	# El segundo build, con las variables vacías. En el Dockerfile `ENV VAR=$$ARG`
	# sin argumento deja la variable en "", no ausente, y el 02-08 eso rompió un
	# deploy entero (new URL("")). El build normal no lo detecta. Faltaba acá, así
	# que el gate nacido de ese incidente era el único que no se podía correr en
	# local: verde en tu máquina no significaba verde en CI.
	cd web && NEXT_PUBLIC_SITE_URL= NEXT_PUBLIC_GOOGLE_CLIENT_ID= API_URL= npm run build

# ---------------------------------------------------------------------------
# Staging local: los mismos contenedores que Coolify arma en producción.
#
# No confundir con `make dev`: ese corre runserver, next dev y SQLite. Esto
# corre gunicorn, la web compilada y Postgres 16 — la misma imagen del VPS.
# Es el único entorno local donde probar el cobro significa algo, porque en
# SQLite la constraint que sostiene la idempotencia del webhook se comporta
# distinto y los tests de concurrencia no corren.
#
# Requiere un runtime de contenedores (OrbStack o Docker Desktop).
# ---------------------------------------------------------------------------
STAGING = docker compose -f compose.staging.yaml --env-file .env.staging

staging-up: .env.staging ## Levanta el staging local (web :3002, backend :8001)
	$(STAGING) up -d --build
	@echo ""
	@echo "  web     → http://localhost:$${WEB_PORT:-3002}"
	@echo "  backend → http://localhost:$${BACK_PORT:-8001}/healthz/"
	@echo "  base    → localhost:$${DB_PORT:-5433}"
	@echo ""
	@echo "  Tu Mac es arm64 y el VPS amd64. Esto builda nativo, que alcanza"
	@echo "  para probar comportamiento. Para verificar el build REAL de"
	@echo "  producción:  DOCKER_DEFAULT_PLATFORM=linux/amd64 make staging-up"

staging-down: ## Baja el staging local (conserva la base)
	$(STAGING) down

staging-logs: ## Sigue los logs del staging local
	$(STAGING) logs -f

staging-reset: ## Borra la base de staging y levanta de cero
	$(STAGING) down -v
	$(STAGING) up -d --build

# Si falta el archivo de entorno, decirlo con una instrucción en vez de que
# docker compose falle con un error críptico sobre una variable no definida.
.env.staging:
	@echo "Falta .env.staging. Crealo con:"
	@echo "    cp .env.staging.example .env.staging"
	@echo "y completá al menos POSTGRES_PASSWORD y SECRET_KEY."
	@exit 1

test-back-pg: .env.staging ## pytest contra el Postgres de staging (corre los tests que SQLite saltea)
	# Por qué existe: `make test-back` usa el default de dj_database_url, que es
	# SQLite. Ahí los 6 tests de tests/api/test_ledger_concurrencia.py se saltean
	# solos (`skipif connection.vendor != "postgresql"`), así que la idempotencia
	# del cobro nunca se prueba en local — igual que advierte el CLAUDE.md.
	# Medido el 28-08-2026: SQLite 1 passed + 6 skipped, Postgres 7 passed.
	# Necesita el staging arriba (`make staging-up`).
	#
	# Toma SÓLO las cuatro variables de conexión, no el .env.staging entero. La
	# primera versión hacía `set -a; . ./.env.staging` y exportaba todo el
	# archivo: `INSTALL_FREE_CREDITS`, `INTERPRETATION_DAILY_CAP`, `SECRET_KEY`
	# y `ANTHROPIC_API_KEY` pisaban los defaults del código, así que este gate y
	# `make test-back` corrían con entornos distintos y sus resultados no eran
	# comparables. El 28-08-2026 eso dio dos tests en rojo acá y en verde allá,
	# por una diferencia de entorno y no de motor de base.
	#
	# HALLAZGO 6 de code review: la versión con `eval "$$(grep ...)"` evaluaba
	# las líneas crudas de `.env.staging` como shell — una contraseña con
	# espacio, `$`, backtick o comilla rompía la asignación o EJECUTABA lo que
	# tuviera adentro. `read` no tiene ese problema: asigna el valor tal cual,
	# sin volver a interpretarlo como código (probado a mano con una
	# contraseña con `$b\`whoami\`` — queda literal, no ejecuta nada). No usa
	# `grep | while read` (un pipe mete el `while` en una subshell y las
	# `export` no sobreviven fuera de ella) ni `<(...)` de bash (no está
	# disponible acá: `/bin/sh` corre en modo POSIX y lo rechaza) — lee
	# `.env.staging` directo con redirección de archivo, que no abre subshell,
	# y filtra las cuatro variables que importan con `case`.
	@while IFS='=' read -r key value; do \
		case "$$key" in \
			POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB|DB_PORT) export "$$key=$$value" ;; \
		esac; \
	done < .env.staging; \
		cd backend && DEBUG=1 \
		DATABASE_URL="postgres://$$POSTGRES_USER:$$POSTGRES_PASSWORD@localhost:$$DB_PORT/$$POSTGRES_DB" \
		.venv/bin/python -m pytest -q

sky: ## Muestra el cielo que devuelve el backend local
	@curl -s http://localhost:$(BACK_PORT)/api/sky/ | python3 -m json.tool
