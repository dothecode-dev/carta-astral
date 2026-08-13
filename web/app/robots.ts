import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/config";

// Las rutas privadas ya se marcan `noindex` en su propia metadata
// (`cuenta`, `carta/[id]`, `nueva`, `entrar`). Acá se bloquea además el rastreo
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
      disallow: ["/api/", "/*/cuenta", "/*/carta/", "/*/nueva"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
