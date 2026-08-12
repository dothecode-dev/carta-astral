# web — la aplicación pública de AstraGuía

Next 16 (App Router) + TypeScript, en español, inglés y portugués. Empezó siendo una
vidriera y hoy es la aplicación entera: portada, alta de carta, lectura, cuenta y login.

Habla con el backend a través de un BFF propio en `app/api/`: el navegador nunca le pega
al backend directo ni ve el token de sesión, que viaja en una cookie `httpOnly`.

## Levantar en local

```bash
make install       # desde la raíz: instala los dos proyectos
npm run dev        # http://localhost:3000 → redirige a /es
```

Instalá con `make install`, no con `npm install` a mano: en macOS `npm install` reescribe
`package-lock.json` sacando las dependencias opcionales de Linux y eso rompe el CI y el
build del Dockerfile. El Makefile usa `npm ci`, que respeta el lock.

Gates, los mismos que corre el CI (o `make test-web` desde la raíz, que los corre todos):

```bash
npx eslint .
npm test
npx tsc --noEmit
npm run check:legal
npm run build
NEXT_PUBLIC_SITE_URL= NEXT_PUBLIC_GOOGLE_CLIENT_ID= API_URL= npm run build
```

El build va **dos veces**. El segundo, con las variables vacías, existe porque en el
Dockerfile un `ENV VAR=$ARG` sin argumento deja la variable en `""` y no ausente: el 02-08
eso rompió un deploy entero con un `new URL("")`. El build normal no lo detecta.

## Cómo está armado

- `app/[locale]/` — las rutas, prerenderizadas en los tres idiomas. No existe ningún otro
  locale: `dynamicParams = false`. Son la portada, `nueva`, `carta/[id]`,
  `carta/[id]/lectura`, `cuenta`, `entrar`, `ejemplo` y `legal/[doc]`.
- `app/api/` — el BFF. `session` canjea el `id_token` de Google contra el backend y guarda
  el token en una cookie `httpOnly`; `charts`, `account`, `geocode` y
  `charts/[id]/interpretation` son los proxies del resto.
- `lib/i18n.ts` — el contenido de las tres versiones. No hay librería de i18n: son tres
  idiomas y un objeto. `tests/i18n.test.ts` verifica que ninguno se quede atrás.
- `lib/session.ts` — el manejo de la cookie y las llamadas al backend.
- `lib/sky.ts` — pide el cielo actual al backend, con timeout de 3 segundos.
- `lib/ephemeris.ts` — posiciones de Sol, Luna y planetas por elementos orbitales de
  Schlyter, con precisión de alrededor de un minuto de arco. Es el **fallback** de la rueda
  de la portada para cuando el backend no responde; el camino normal es el endpoint de
  efemérides. Las cartas natales las calcula siempre el backend con Swiss Ephemeris.
- `components/` — piezas con test propio: `GoogleSignIn`, `Nav`, `StoreBadges`,
  `NewChartForm`, `AspectMatrix`, `SolarSystem`, `ChartActions`, `AccountCharts`,
  `DangerZone`, `ThemeSwitch`.
- `app/globals.css` — el sistema visual. Los tokens de NOCHE son los mismos que la app;
  DÍA es su inversión, con el dorado bajado para que tenga contraste sobre fondo claro.
- `app/healthz` — liveness para Coolify.

Las fuentes se sirven desde `public/fonts` con `next/font/local`: Fraunces para los
títulos, Outfit para el cuerpo (continuidad con la app) y Space Mono para todo lo que es
dato.

## Deploy

Imagen autocontenida (`output: "standalone"`), que corre como usuario sin privilegios:

```bash
docker build -t astra-web .
docker run -p 3000:3000 astra-web
```

En Coolify: aplicación por Dockerfile, base directory `web`, puerto 3000, healthcheck
`/healthz`.

Las variables `NEXT_PUBLIC_*` van como **build args**, no como variables de runtime: se
incrustan al compilar. Si no llegan al build, el bundle sale sin ellas y el login no
encuentra su credencial.

Coolify despliega cada aplicación con lo que cambia en su carpeta, filtrando por Watch
Paths. El patrón va con **doble** asterisco (`web/**`): con uno solo no matchea rutas
anidadas y los push se descartan en silencio con "Changed files do not match watch paths".

## Pendientes

- Los badges de App Store y Google Play están dibujados a mano (`components/StoreBadges.tsx`).
  Antes de publicar hay que reemplazarlos por los oficiales de cada tienda, que tienen
  guías de marca obligatorias.
- Los badges no son navegables y muestran un cartel de próximamente: las apps todavía no
  existen. Cuando se publiquen, vuelven a ser enlaces y se saca el cartel.
- El cobro de la web (Paddle) no está integrado todavía.
