# carta-astral

Cálculo e interpretación de cartas natales. Backend Django + DRF y web pública en Next.

El backend (`backend/`) hace el cálculo astrológico (`core/`), geocodifica los lugares de
nacimiento con GeoNames, genera la interpretación en lenguaje natural con Claude
(`interpret/`), lleva un ledger de créditos y sirve el blog desde un CMS Wagtail (`cms/`).
La web (`web/`) es la aplicación pública: portada, alta de carta, lectura, cuenta y login
con Google, en español, inglés y portugués.

La app móvil (React Native) es un repositorio aparte. La superficie de backend que la
servía —compras in-app y login con Apple— está en este repo pero apagada detrás de
`APP_AUTH_ENABLED` e `IAP_WEBHOOK_ENABLED` mientras la app no se retome.

## Desarrollo local

```bash
make install   # dependencias de los dos proyectos, y web/.env.local
make dev       # backend en :8000 y web en :3000, juntos
make test      # los mismos gates que corre el CI
```

`make dev` deja la web apuntando al backend de tu máquina, así que se trabaja contra datos
reales sin tocar producción. Si el backend no está levantado la web funciona igual: la
rueda de la portada cae a un cálculo local.

Dos comandos más que ahorran tiempo: `make stop` libera los puertos cuando queda algo
colgado, y `make sky` muestra lo que devuelve el endpoint de efemérides. `make help` los
lista todos.

**Los tests del backend corren contra SQLite salvo que definas `DATABASE_URL`, y el CI
corre contra Postgres 16.** No es un detalle: la `UniqueConstraint` parcial que sostiene la
idempotencia del webhook de pagos tiene otra semántica en SQLite, y los tests de
concurrencia no corren ahí porque SQLite ignora `SELECT ... FOR UPDATE`. Si tocás cobro o
ledger, corré contra Postgres o no probaste nada.

Cada carpeta se despliega por su cuenta con su propio `Dockerfile`; nada de esto cambia
cómo se construye en producción. Las variables del backend se documentan en
`backend/.env.example`, que un test mantiene completo.

## Licencia

Este proyecto se distribuye bajo **GNU Affero General Public License v3.0** (AGPL-3.0).
Ver [`LICENSE`](LICENSE).

Si ofrecés este software como servicio en red, la AGPL te obliga a poner el código fuente
completo a disposición de los usuarios del servicio.

## Atribución

El cálculo astrológico usa [Swiss Ephemeris](https://www.astro.com/swisseph/) a través
de [`pyswisseph`](https://github.com/astrorigin/pyswisseph) y
[`kerykeion`](https://github.com/g-battaglia/kerykeion). Swiss Ephemeris está licenciado
bajo AGPL-3.0 (o licencia comercial). El uso público de este proyecto bajo AGPL-3.0 es
consecuencia directa de esa licencia.

Datos de lugares: [GeoNames](https://www.geonames.org/) (CC BY 4.0).
