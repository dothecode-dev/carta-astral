import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/config";

// Las rutas privadas ya se marcan `noindex` en su propia metadata
// (`cuenta`, `carta/[id]`, `entrar`). `nueva` NO: es el calculador abierto, está
// en el sitemap y es indexable desde el 04-09-2026. Seguía en este `disallow` y
// Google la tuvo un mes sin rastrear (`tests/robots-sitemap.test.ts` cruza los
// dos archivos para que no vuelva a pasar). Acá se bloquea además el rastreo
// de las que exigen sesión: sin cookie devuelven un redirect al login, así que
// recorrerlas sólo gasta presupuesto de rastreo.
//
// `entrar` queda fuera de la lista a propósito: es `noindex` pero `follow`, y
// bloquear su rastreo impediría que Google siga los enlaces legales del pie.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // `/rueda` es el proxy de PostHog, no una página: rastrearlo es gastar
      // presupuesto en respuestas de una API de terceros.
      disallow: ["/api/", "/rueda/", "/*/cuenta", "/*/carta/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
