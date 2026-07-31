# web — la vidriera de ASTRA

Next 16 (App Router) + TypeScript. Sirve la home pública en español, inglés y
portugués. No habla con el backend: todo lo que muestra es contenido propio o se
calcula en el navegador.

## Levantar en local

```bash
npm install
npm run dev        # http://localhost:3000 → redirige a /es
```

Gates, los mismos que corre el CI:

```bash
npx eslint .
npx tsc --noEmit
npm run build
```

## Cómo está armado

- `app/[locale]/` — las tres rutas (`/es`, `/en`, `/pt`), prerenderizadas. No
  existe ningún otro locale: `dynamicParams = false`.
- `lib/i18n.ts` — el contenido de las tres versiones. No hay librería de i18n:
  son tres idiomas y un objeto.
- `lib/ephemeris.ts` — posiciones de Sol, Luna y planetas por elementos
  orbitales de Schlyter, con precisión de alrededor de un minuto de arco. Es la
  rueda de la portada, no una carta natal: las cartas las calcula el backend con
  Swiss Ephemeris.
- `app/globals.css` — el sistema visual. Los tokens de NOCHE son los mismos que
  la app (`carta-astral-app/src/theme/tokens.ts`); DÍA es su inversión, con el
  dorado bajado para que tenga contraste sobre fondo claro.
- `app/healthz` — liveness para Coolify.

Las fuentes se sirven desde `public/fonts` con `next/font/local`: Fraunces para
los títulos, Outfit para el cuerpo (continuidad con la app) y Space Mono para
todo lo que es dato.

## Deploy

Imagen autocontenida (`output: "standalone"`), unos 74 MB, corre como usuario
sin privilegios:

```bash
docker build -t astra-web .
docker run -p 3000:3000 astra-web
```

En Coolify: aplicación por Dockerfile, base directory `web`, puerto 3000,
healthcheck `/healthz`.

## Pendientes

- Los links del navbar y "Ver una carta de ejemplo" apuntan a `#`: esas páginas
  todavía no existen.
- Los badges de App Store y Google Play están dibujados a mano. Antes de
  publicar hay que reemplazarlos por los oficiales de cada tienda, que tienen
  guías de marca obligatorias.
- La rueda se calcula en el cliente. Cuando el backend exponga el endpoint
  público de efemérides, pasa a Swiss Ephemeris.
