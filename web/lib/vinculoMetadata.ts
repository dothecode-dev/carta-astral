import type { Metadata } from "next";

import { VINCULO } from "@/content/vinculo";
import { SITE_URL } from "@/lib/config";
import { DEFAULT_LOCALE, LOCALES, SYNASTRY_SLUG } from "@/lib/i18n";
import { localeDelVinculo } from "@/lib/vinculo";

// La landing de Vínculo vive en dos carpetas —`sinastria` (es y pt) y
// `synastry` (en)— porque el slug cambia con el idioma. Cada una tiene que ser
// una página completa (lo exige `tests/esqueleto.test.ts`, que lee el
// `page.tsx`), así que lo que comparten está acá. Mismo reparto que
// `lib/cielo.ts`.

export function vinculoMetadata(locale: string, slug: string): Metadata {
  const code = localeDelVinculo(locale, slug);
  if (!code) return {};

  const t = VINCULO[code];
  const title = `${t.metaTitle} · ASTRA`;
  const url = `${SITE_URL}/${code}/${SYNASTRY_SLUG[code]}`;

  return {
    title,
    description: t.metaDescription,
    alternates: {
      canonical: url,
      languages: {
        ...Object.fromEntries(
          LOCALES.map((l) => [l, `${SITE_URL}/${l}/${SYNASTRY_SLUG[l]}`]),
        ),
        // Sin esta línea la página queda sin `x-default` y, a quien no le calza
        // ninguno de los tres idiomas, Google le elige uno.
        "x-default": `${SITE_URL}/${DEFAULT_LOCALE}/${SYNASTRY_SLUG[DEFAULT_LOCALE]}`,
      },
    },
    openGraph: {
      type: "website",
      siteName: "ASTRA",
      locale: code,
      title,
      description: t.metaDescription,
      url,
    },
    twitter: { card: "summary_large_image", title, description: t.metaDescription },
  };
}
