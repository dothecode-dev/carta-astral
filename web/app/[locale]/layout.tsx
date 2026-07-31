import type { Metadata } from "next";
import localFont from "next/font/local";
import { notFound } from "next/navigation";

import "../globals.css";
import { DEFAULT_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";

// Fraunces lleva la voz de los títulos; Outfit el cuerpo, en continuidad con la
// app; Space Mono todo lo que es dato (grados, fechas, precios).
const display = localFont({
  src: "../../public/fonts/fraunces.woff2",
  variable: "--font-display",
  weight: "300 600",
  display: "swap",
});

const body = localFont({
  src: "../../public/fonts/outfit.woff2",
  variable: "--font-body",
  weight: "300 500",
  display: "swap",
});

const mono = localFont({
  src: "../../public/fonts/spacemono.woff2",
  variable: "--font-mono",
  weight: "400",
  display: "swap",
});

// Corre antes del primer paint: sin esto la página parpadea en el tema
// equivocado durante un frame.
const THEME_SCRIPT = `try{var t=localStorage.getItem("astra-theme");if(t==="dark"||t==="light"){document.documentElement.dataset.theme=t}}catch(e){}`;

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

// Sólo existen /es, /en y /pt: cualquier otro valor del segmento da 404 sin
// llegar a ejecutar nada.
export const dynamicParams = false;

// Google exige URLs absolutas en canonical y hreflang; con metadataBase, Next
// resuelve las relativas de abajo contra este origen.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://astra.dothecode.com";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const dict = getDict(isLocale(locale) ? locale : DEFAULT_LOCALE);
  return {
    metadataBase: new URL(SITE_URL),
    title: dict.meta.title,
    description: dict.meta.description,
    alternates: {
      canonical: `/${locale}`,
      languages: Object.fromEntries(LOCALES.map((code) => [code, `/${code}`])),
    },
    openGraph: {
      type: "website",
      siteName: "ASTRA",
      locale,
      title: dict.meta.title,
      description: dict.meta.description,
      url: `/${locale}`,
    },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  return (
    <html lang={locale} className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        {children}
      </body>
    </html>
  );
}
