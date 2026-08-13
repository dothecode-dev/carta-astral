import type { Metadata } from "next";
import localFont from "next/font/local";
import { notFound } from "next/navigation";

import "../globals.css";
import { DEFAULT_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";

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
      languages: {
        ...Object.fromEntries(LOCALES.map((code) => [code, `/${code}`])),
        // A quien no le calce ninguno de los tres idiomas, Google le muestra
        // éste. Sin declararlo elige por su cuenta, y suele elegir mal.
        "x-default": `/${DEFAULT_LOCALE}`,
      },
    },
    openGraph: {
      type: "website",
      siteName: "ASTRA",
      locale,
      title: dict.meta.title,
      description: dict.meta.description,
      url: `/${locale}`,
    },
    // X y las apps de mensajería usan la imagen de Open Graph si no hay una
    // propia; lo único que falta declarar es que la muestren grande.
    twitter: {
      card: "summary_large_image",
      title: dict.meta.title,
      description: dict.meta.description,
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
    // El script de abajo escribe data-theme antes de que React hidrate, así que
    // el atributo del servidor y el del DOM no coinciden por diseño.
    <html
      lang={locale}
      className={`${display.variable} ${body.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Corre antes del primer paint para que la página no parpadee en el
            tema equivocado. Es la misma técnica que usa next-themes.

            En desarrollo React avisa "Encountered a script tag while rendering
            React component": es esperado y no hay forma de evitarlo sin perder
            algo. La única alternativa real —guardar el tema en una cookie y
            escribir data-theme desde el servidor— haría que las tres rutas
            dejen de ser estáticas. En producción el aviso no aparece. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
