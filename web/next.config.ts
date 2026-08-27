import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Imagen de producción autocontenida para el contenedor de Coolify.
  output: "standalone",

  // El proxy de PostHog NO va acá, no hay `rewrites`: un rewrite a un host
  // externo reenvía las cabeceras de entrada tal cual, con la cookie de sesión
  // adentro. Está medido y documentado en `app/rueda/[...path]/route.ts`.
  //
  // Esto sí queda, y es una concesión conocida: la API de PostHog usa rutas con
  // barra final (`/e/`) y sin esto Next devuelve un 308 antes de llegar al
  // handler — un redirect por evento, medido. El costo es que la opción es
  // global: todas las páginas del sitio pasan a responder 200 con y sin barra
  // final en vez de redirigir a una sola forma. Las páginas indexables declaran
  // su `canonical` en `generateMetadata`, así que los buscadores las colapsan.
  skipTrailingSlashRedirect: true,

  async redirects() {
    // La raíz manda al idioma por defecto. Va acá y no en proxy.ts porque es un
    // redirect fijo que no necesita mirar la request: lo recomienda la doc de Next 16.
    return [{ source: "/", destination: "/es", permanent: false }];
  },
};

export default nextConfig;
