import type { MetadataRoute } from "next";

import { LEGAL_UPDATED } from "@/content/legal/types";
import { DEFAULT_LOCALE, LOCALES, NOTES_SLUG, type Locale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { fetchNotesOrNone } from "@/lib/notes";

// Sólo lo que es público e indexable. Las páginas con sesión (`cuenta`,
// `carta/[id]`, `nueva`) y la de acceso son `noindex` y no entran acá.
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

/** Las notas publicadas de un idioma, cada una con su fecha real.
 *
 * Sin `alternates`: cada idioma tiene su propia nota, con su propio slug, y una
 * puede estar publicada en español y todavía no en inglés. La sección sí se
 * declara traducida, porque las tres existen siempre. */
async function noteEntries(locale: Locale): Promise<MetadataRoute.Sitemap> {
  // Si el CMS no contesta, el sitemap sale sin notas en vez de tirar el build.
  const notes = await fetchNotesOrNone(locale);
  return notes.map((note) => ({
    url: `${SITE_URL}/${locale}/${NOTES_SLUG[locale]}/${note.slug}`,
    lastModified: note.fecha,
    changeFrequency: "yearly" as const,
    priority: 0.6,
  }));
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const notes = (await Promise.all(LOCALES.map(noteEntries))).flat();

  const sections = LOCALES.map((locale) => ({
    url: `${SITE_URL}/${locale}/${NOTES_SLUG[locale]}`,
    changeFrequency: "weekly" as const,
    priority: 0.7,
    alternates: {
      languages: {
        ...Object.fromEntries(
          LOCALES.map((code) => [code, `${SITE_URL}/${code}/${NOTES_SLUG[code]}`]),
        ),
        "x-default": `${SITE_URL}/${DEFAULT_LOCALE}/${NOTES_SLUG[DEFAULT_LOCALE]}`,
      },
    },
  }));

  const fixed = LOCALES.flatMap((locale) =>
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

  return [...fixed, ...sections, ...notes];
}
