import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CieloHoy } from "@/components/CieloHoy";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { cieloMetadata, localeDelCielo } from "@/lib/cielo";
import { SKY_SLUG, getDict } from "@/lib/i18n";
import { haySesion } from "@/lib/session";
import { fetchMoon, fetchSky } from "@/lib/sky";

// «El cielo de hoy». Las tres carpetas del slug traducido son copias de esta
// forma: ver `lib/cielo.ts`.
const SLUG = "ceu-hoje";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return cieloMetadata(locale, SLUG);
}

export default async function CeuHojePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: segmento } = await params;
  const locale = localeDelCielo(segmento, SLUG);
  if (!locale) notFound();

  const dict = getDict(locale);
  const [sky, moon, signedIn] = await Promise.all([fetchSky(), fetchMoon(), haySesion()]);

  return (
    <>
      <Nav locale={locale} dict={dict} path={(code) => `/${SKY_SLUG[code]}`} signedIn={signedIn} />
      <main className="docFrame chartFrame">
        <CieloHoy locale={locale} sky={sky} moon={moon} ahora={new Date()} />
      </main>
      <Footer locale={locale} dict={dict} />
    </>
  );
}
