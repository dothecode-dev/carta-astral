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

.DEFAULT_GOAL := help
.PHONY: help dev back web stop install test test-back test-web sky

help: ## Muestra estos comandos
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

dev: stop ## Levanta backend y web juntos (Ctrl-C corta los dos)
	@echo "  backend → http://localhost:$(BACK_PORT)"
	@echo "  web     → http://localhost:$(WEB_PORT)"
	@echo ""
	@trap 'kill 0' EXIT INT TERM; \
		(cd backend && DEBUG=1 .venv/bin/python manage.py runserver $(BACK_PORT)) & \
		(cd web && npm run dev -- --port $(WEB_PORT)) & \
		wait

back: ## Sólo el backend
	cd backend && DEBUG=1 .venv/bin/python manage.py runserver $(BACK_PORT)

web: ## Sólo la web
	cd web && npm run dev -- --port $(WEB_PORT)

stop: ## Libera los puertos (mata lo que haya quedado colgado)
	@lsof -ti:$(BACK_PORT) | xargs kill -9 2>/dev/null || true
	@lsof -ti:$(WEB_PORT) | xargs kill -9 2>/dev/null || true

install: ## Instala las dependencias de los dos proyectos
	cd backend && uv sync
	cd web && npm install
	@test -f web/.env.local || cp web/.env.example web/.env.local
	@echo "listo — 'make dev' para levantar todo"

test: test-back test-web ## Corre todos los gates, los mismos que el CI

test-back: ## Gates del backend: pytest, ruff, contratos, tipos
	cd backend && DEBUG=1 .venv/bin/python -m pytest -q
	cd backend && .venv/bin/ruff check .
	cd backend && .venv/bin/lint-imports
	cd backend && .venv/bin/mypy

test-web: ## Gates de la web: eslint, tipos, legales, build
	cd web && npx eslint .
	cd web && npx tsc --noEmit
	cd web && npm run check:legal
	cd web && npm run build

sky: ## Muestra el cielo que devuelve el backend local
	@curl -s http://localhost:$(BACK_PORT)/api/sky/ | python3 -m json.tool
