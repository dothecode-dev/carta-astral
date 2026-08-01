# carta-astral

Backend de cálculo e interpretación de cartas natales. API Django + DRF: cálculo
astrológico (`core/`), geocodificación de lugares de nacimiento (GeoNames) e
interpretación en lenguaje natural con Claude.

El código del backend vive en [`backend/`](backend/) y la web pública en
[`web/`](web/). La app móvil (React Native) es un repositorio aparte.

## Desarrollo local

```bash
make install   # dependencias de los dos proyectos, y web/.env.local
make dev       # backend en :8000 y web en :3000, juntos
make test      # los mismos gates que corre el CI
```

`make dev` deja la web apuntando al backend de tu máquina, así que se trabaja
contra datos reales sin tocar producción. Si el backend no está levantado la web
funciona igual: la rueda de la portada cae a un cálculo local.

Dos comandos más que ahorran tiempo: `make stop` libera los puertos cuando queda
algo colgado, y `make sky` muestra lo que devuelve el endpoint de efemérides.

Cada carpeta se despliega por su cuenta con su propio `Dockerfile`; nada de esto
cambia cómo se construye en producción.

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
