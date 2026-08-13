# carta-astral — reglas del repo

ASTRA: cálculo e interpretación de cartas natales. Dos proyectos que se despliegan
por separado y viven acá: `backend/` (Django + DRF) y `web/` (Next). La app móvil
(React Native) es **otro repositorio**; si el pedido habla de la app, no está acá.

La app no se retoma por ahora: se termina la web, con cobro propio. La superficie de
backend que servía a la app —login con Apple y webhook de compras in-app— sigue en el
repo pero **apagada** por `APP_AUTH_ENABLED` e `IAP_WEBHOOK_ENABLED`, las dos en `0`.
No se borró nada: cuando la app vuelva se prende la plataforma que corresponda. Si
tocás esa superficie, sus tests encienden el flag donde configuran sus credenciales.

Leé también `web/AGENTS.md` cuando toques la web.

## Este repositorio es público

Está publicado bajo AGPL-3.0 y no es una elección revisable: el cálculo usa
`kerykeion` y `pyswisseph`, que son AGPL, y eso obliga a publicar el fuente. No
propongas hacerlo privado.

La consecuencia práctica es que **todo lo que commitees es público**:

- Nada de credenciales, tokens ni claves en el código. Todo por variables de entorno.
- `docs/` está en `.gitignore` a propósito (specs con modelo de negocio y análisis
  de seguridad). No lo agregues al repo ni pegues su contenido en código o READMEs.
- `*.p8`, `*.pem`, `*.keystore`, `*.jks` y `LEEME-*.txt` están ignorados: son claves
  privadas reales. Nunca los fuerces con `git add -f`.
- `backend/.env` está ignorado por `backend/.gitignore`. Si agregás una variable
  nueva, sumala a `backend/.env.example` con el valor vacío o de ejemplo, nunca el real.
  Esto **no depende de que te acuerdes**: `tests/test_env_example.py` recorre todo
  `backend/` buscando lecturas de `os.environ` y falla si alguna no está documentada,
  y un segundo test falla si algún valor parece real.

## Levantar y verificar

```bash
make install   # deps de los dos proyectos + web/.env.local
make dev       # backend en :8000 y web en :3000, juntos (Ctrl-C corta los dos)
make test      # los mismos gates que corre el CI
make stop      # libera los puertos si quedó algo colgado
```

Instalá con `make install`, nunca con `npm install` a mano: en macOS ese comando
reescribe `package-lock.json` sacando las dependencias opcionales de Linux y rompe el
CI y el build del Dockerfile. El Makefile usa `npm ci`.

`make test` es el contrato: si pasa en tu máquina, pasa en CI. Corré al menos los
gates del área que tocaste (`make test-back` / `make test-web`) antes de decir que
algo está listo, y reportá la salida real. Si un gate ya venía fallando antes de tu
cambio, decilo igual en vez de dejarlo pasar en silencio.

Los gates son: backend `pytest`, `ruff`, `lint-imports`, `mypy` (strict, sólo sobre
`core/`) y `makemigrations --check`; web `eslint`, `vitest`, `tsc --noEmit`,
`check:legal` y `next build` (dos veces: una normal y otra con las variables de
entorno vacías, porque en el Dockerfile un `ARG` ausente deja la variable en `""` y
eso ya rompió un deploy).

**CI corre contra Postgres 16, no SQLite**, y no es un detalle: la `UniqueConstraint`
parcial que sostiene la idempotencia del webhook de pagos tiene otra semántica en
SQLite, y los tests de concurrencia no corren ahí (SQLite ignora `SELECT ... FOR
UPDATE`). Si un test de concurrencia o de cobro "pasa" en local con SQLite, no probaste
nada. En desarrollo el Makefile además fuerza `USE_DB_CACHE=1` para que el lock que
impide generar dos veces la misma lectura exista entre procesos, como en producción.

## Arquitectura: la chequea `lint-imports`, no la prosa

Los contratos viven en `[tool.importlinter]` de `backend/pyproject.toml` y fallan el
build. En resumen: `core/` (efemérides, modelos de dominio, conversión de tiempo) no
importa Django, `requests`, `anthropic`, `interpret` ni `api`; `interpret/` (prompts y
generación con Claude) no importa Django ni `api`; y `cms/` (Wagtail) y `api/` no se
importan entre sí. Si necesitás cruzar una de esas fronteras, el problema es el diseño
—hablalo antes—, no el contrato.

`api/` es la capa HTTP y ya es grande: si vas a sumar lógica, va en un módulo de
servicio (`chart_service.py`, `interpretation_service.py`, `ledger.py` son el patrón),
no en `views.py`.

## Superficies críticas

Créditos y ledger, webhooks de pago, autenticación y SSO (Apple/Google), borrado de
cuenta y permisos. Ahí no se improvisa: mini-spec previa y tests antes del código.
Si vas a tocar una y no hay test que cubra el caso, escribilo primero.

## Cómo trabajar

- **Evidencia antes de arreglar.** No toques código por una suposición: conseguí un
  log, una respuesta HTTP, un test que falle. Si el flujo es navegador → servidor →
  backend, probar sólo el backend no prueba el flujo.
- Nunca `except Exception: pass` mudo — mínimo un log estructurado.
- Nunca SQL por interpolación de strings: ORM o consultas parametrizadas.
- Antes de crear un módulo o componente nuevo, buscá si ya existe algo equivalente.
- Si una decisión no estaba en el pedido, preguntá en vez de avanzar en silencio.
- `web/` corre una versión de Next con cambios de ruptura respecto de lo que el modelo
  tiene entrenado: leé la guía correspondiente en `node_modules/next/dist/docs/` antes
  de escribir código de la web.

## Git

Los mensajes de commit no llevan trailer `Co-Authored-By` ni menciones a Claude,
Anthropic o IA — tampoco en descripciones de PR. Autoría humana solamente.

**Se pushea directo a `main`. No hay PR ni aprobación.** Somos dos personas: pedir la
aprobación de alguien era un trámite que terminaba salteándose con `--admin`, y una regla
que se saltea siempre no es una regla. La protección de rama se quitó el 13-08-2026.

El gate no desapareció, se mudó a tu máquina: **`.githooks/pre-push` corre los mismos
gates que el CI y aborta el push si algo falla**, sólo sobre el área que tocaste. Lo
activa `make install` (`core.hooksPath` es config local de cada clon, no viaja con el
repo). Si clonaste a mano, corré `git config core.hooksPath .githooks` o no tenés ningún
freno.

`git push --no-verify` lo saltea. Es para emergencias, no para cuando molesta: entre junio
y agosto de 2026, con push directo y sin este hook, `main` estuvo ocho días en rojo con
los tests de subidas maliciosas del CMS sin verificar y nadie se enteró.

El CI sigue corriendo sobre `main` y es la segunda red, no la primera. Si lo ves en rojo,
lo que hay en `main` está roto de verdad — nadie lo frenó antes.

Si algún cambio sí amerita revisión —una superficie crítica, algo que quieras discutir—,
hacé una rama y un PR igual. Deja de ser obligatorio, no imposible.
