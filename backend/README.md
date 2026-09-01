# backend — API de cartas natales

Django 6 + DRF. Calcula la carta a partir de fecha, hora y lugar de nacimiento, genera la
interpretación con Claude, lleva los derechos de compra por producto (modelo de canje) y
sirve el blog desde Wagtail.

Dependencias con `uv`, Python ≥3.12.

## Los cuatro módulos, y sus fronteras

La arquitectura no vive en este archivo: la chequean los contratos de
`[tool.importlinter]` en `pyproject.toml`, y **fallan el build**.

- **`core/`** — efemérides, modelos de dominio y conversión de tiempo. No importa Django,
  `requests`, `anthropic`, `interpret` ni `api`. Además `core.models` no importa
  `kerykeion`. Es el único módulo con `mypy` en strict.
- **`interpret/`** — prompts y generación de texto con Claude. No importa Django, `api` ni
  `requests`.
- **`api/`** — la capa HTTP. `cms` y `api` no se importan entre sí en ninguna dirección.
- **`cms/`** — el blog en Wagtail, headless.

Fuera de contrato quedan `config/` (settings y urls) y `tests/`.

Si hace falta cruzar una frontera, el problema es de diseño: se habla antes, no se toca el
contrato.

**`api/views.py` ya es grande.** La lógica nueva va en un módulo de servicio —
`chart_service.py`, `interpretation_service.py`, `canje.py`, `chart_pdf_service.py` son
el patrón — nunca en `views.py`.

### El PDF de la carta

`POST /api/charts/{uuid}/pdf/` arma el documento con WeasyPrint. Dos cosas que conviene
saber antes de tocarlo:

- **El backend no sabe dibujar la rueda y no tiene que aprender.** La geometría la calcula
  `astra-wheel` en el navegador y viaja en el cuerpo del pedido, junto con los rótulos ya
  traducidos: acá no hay trigonometría ni diccionario de nombres. Lo que entra son números
  y texto, validados por `api/pdf_payload.py`; el SVG y el HTML los construye
  `chart_pdf_service.py`. Generar markup es seguro, filtrarlo no.
- **El generador tiene prohibido salir a la red.** WeasyPrint resuelve URLs por su cuenta
  —`<img src>`, `<image href>`, `background-image`— y llega hasta el endpoint de metadata
  de la instancia. El `url_fetcher` del servicio sólo deja pasar `data:`, que son las
  tipografías que embebe ese mismo módulo.

La imagen necesita las libs de Pango y `fonts-dejavu-core`: los glifos astrológicos no
están en las tipografías de marca. Ningún gate construye la imagen, así que después de
tocar el `Dockerfile` hay que generar un PDF adentro y mirarlo.

## Configuración

Copiá `.env.example` a `.env` y completá. El molde está completo y lo mantiene así
`tests/test_env_example.py`, que recorre todo `backend/` buscando lecturas de `os.environ`
y falla si alguna no está documentada. Un segundo test verifica que no se filtre ningún
valor real: **el repositorio es público**.

Varias variables son fail-fast: sin `SECRET_KEY`, `WAGTAILADMIN_BASE_URL` o `WEB_BASE_URL`
el proceso no arranca fuera de `DEBUG`. Los paneles de administración sólo se montan si
`ADMIN_URL` y `WAGTAIL_ADMIN_URL` están definidas, y en la ruta que digan: sin ellas, no
existen.

La superficie de la app móvil —login con Apple y webhook de compras in-app— está apagada
por `APP_AUTH_ENABLED` e `IAP_WEBHOOK_ENABLED`, ambas en `0` por defecto. El código no se
borró: cuando la app vuelva, se prende la plataforma que corresponda.

## Correr los tests

Desde la raíz del repo, `make test-back` corre los cinco gates: `pytest`, `ruff`,
`lint-imports`, `mypy` y `makemigrations --check`.

**Por defecto usan SQLite, y el CI usa Postgres 16.** La `UniqueConstraint` parcial que da
idempotencia al webhook de pagos tiene otra semántica en SQLite, y los tests de
concurrencia del canje no corren ahí porque SQLite ignora `SELECT ... FOR UPDATE`. Para
tocar cobro, derechos o canje, apuntá a un Postgres real:

```bash
DATABASE_URL=postgres://usuario:clave@localhost:5432/carta_test \
  .venv/bin/python -m pytest -q
```

## Producción

El `Dockerfile` compila `pyswisseph` en una etapa aparte (necesita `gcc`) y corre
`collectstatic` en build; la imagen final no lleva compilador. `entrypoint.sh` aplica
migraciones y crea la tabla de cache en cada arranque, que es idempotente.

Dos cosas que el arranque **no** hace y hay que recordar:

- **Montar un volumen persistente en `/data/media`.** Sin él, cada deploy borra las
  imágenes del CMS y deja las referencias colgadas en la base.
- **Cargar GeoNames**, una sola vez y antes de exponer el dominio:
  `python manage.py import_geonames`. Trunca y recarga unas 234k filas, así que con
  tráfico vivo deja la geocodificación rota durante toda la carga.

`USE_DB_CACHE=1` es obligatorio fuera de `DEBUG`: el throttle, el tope diario de costo y el
lock que impide generar dos veces la misma lectura viven en la cache, y con la de memoria
cada worker tendría la suya —o sea, ningún límite real.
