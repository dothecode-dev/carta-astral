# carta-astral

Backend de cálculo e interpretación de cartas natales. API Django + DRF: cálculo
astrológico (`core/`), geocodificación de lugares de nacimiento (GeoNames) e
interpretación en lenguaje natural con Claude.

El código del backend vive en [`backend/`](backend/). El frontend es una app móvil
(React Native) separada.

## Licencia

Este proyecto se distribuye bajo **GNU Affero General Public License v3.0** (AGPL-3.0).
Ver [`LICENSE`](LICENSE).

Si ofrecés este software como servicio en red, la AGPL te obliga a poner el código
fuente completo a disposición de los usuarios del servicio.

## Atribución

El cálculo astrológico usa [Swiss Ephemeris](https://www.astro.com/swisseph/) a través
de [`pyswisseph`](https://github.com/astrorigin/pyswisseph) y
[`kerykeion`](https://github.com/g-battaglia/kerykeion). Swiss Ephemeris está licenciado
bajo AGPL-3.0 (o licencia comercial). El uso público de este proyecto bajo AGPL-3.0 es
consecuencia directa de esa licencia.

Datos de lugares: [GeoNames](https://www.geonames.org/) (CC BY 4.0).
