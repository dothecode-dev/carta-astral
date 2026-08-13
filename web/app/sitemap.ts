import type { MetadataRoute } from "next";

import { LEGAL_UPDATED } from "@/content/legal/types";
import { DEFAULT_LOCALE, LOCALES } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";

// Sólo lo que es público e indexable. Las páginas con sesión (`cuenta`,
// `carta/[id]`, `nueva`) y la de acceso son `noindex` y no entran acá.
//
// Las notas del CMS todavía no tienen ruta en la web; cuando la tengan, se
// suman a esta lista leyendo la API de Wagtail.
const PATHS = ["", "/ejemplo", "/legal/privacy", "/legal/terms"] as const;

function url(locale: string, path: string) {
  return `${SITE_URL}/${locale}${path}`;
}

/** Las tres versiones de una ruta, más el `x-default` que atiende al resto. */
function languagesFor(path: string) {
  return {
    ...Object.fromEntries(LOCALES.map((locale) => [locale, url(locale, path)])),
    "x-default": url(DEFAULT_LOCALE, path),
  };
}

export default function sitemap(): MetadataRoute.Sitemap {
  return LOCALES.flatMap((locale) =>
    PATHS.map((path) => ({
      url: url(locale, path),
      // Sólo se declara donde hay una fecha real: los documentos legales llevan
      // la de su última revisión. Poner la del build en todo lo demás sería
      // decir que la página cambió en cada deploy, y Google deja de creerle a
      // un `lastmod` que miente.
      ...(path.startsWith("/legal/") ? { lastModified: LEGAL_UPDATED } : {}),
      changeFrequency: path === "" ? ("weekly" as const) : ("monthly" as const),
      priority: path === "" ? 1 : path === "/ejemplo" ? 0.8 : 0.3,
      alternates: { languages: languagesFor(path) },
    })),
  );
}
