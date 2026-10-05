import type { Metadata } from "next";

import { CIELO } from "@/content/cielo";
import { SITE_URL } from "@/lib/config";
import { DEFAULT_LOCALE, LOCALES, SKY_SLUG, isLocale, type Locale } from "@/lib/i18n";

// «El cielo de hoy» vive en tres carpetas —`cielo-hoy`, `sky-today`,
// `ceu-hoje`— porque el slug cambia con el idioma. Cada una tiene que ser una
// página completa (lo exige `tests/esqueleto.test.ts`, que lee el `page.tsx`),
// así que lo que comparten está acá.

/** El idioma de la ruta, o `null` si no corresponde a ese slug: `/en/cielo-hoy`
 *  existe como carpeta, pero no es una página. */
export function localeDelCielo(locale: string, slug: string): Locale | null {
  return isLocale(locale) && SKY_SLUG[locale] === slug ? locale : null;
}

export function cieloMetadata(locale: string, slug: string): Metadata {
  const code = localeDelCielo(locale, slug);
  if (!code) return {};
  const t = CIELO[code];
  return {
    metadataBase: new URL(SITE_URL),
    title: `${t.metaTitle} — ASTRA`,
    description: t.metaDescription,
    alternates: {
      canonical: `/${code}/${SKY_SLUG[code]}`,
      languages: {
        ...Object.fromEntries(LOCALES.map((l) => [l, `/${l}/${SKY_SLUG[l]}`])),
        "x-default": `/${DEFAULT_LOCALE}/${SKY_SLUG[DEFAULT_LOCALE]}`,
      },
    },
  };
}
