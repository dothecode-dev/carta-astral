import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Nav } from "@/components/Nav";
import { NewChartForm } from "@/components/NewChartForm";
import { DEFAULT_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { haySesion } from "@/lib/session";
import { Footer } from "@/components/Footer";

// Se entra sin cuenta desde el 04-09-2026. Antes esta página redirigía al
// login: el CTA de la home terminaba acá, así que el visitante frío —el de una
// búsqueda, el de Instagram— chocaba con un registro antes de ver nada,
// mientras /precios le prometía tres lecturas gratis. Ahora calcula su carta y
// la ve; la cuenta se pide para la lectura escrita, que es lo que cuesta.
//
// Y es indexable, que es la otra mitad: "calcular carta natal gratis" es la
// búsqueda del rubro, y una página que redirige al login no la puede atender.

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const t = getDict(locale).newChart;
  return {
    title: `${t.seoTitle} · ASTRA`,
    description: t.seoDescription,
    alternates: {
      canonical: `${SITE_URL}/${locale}/nueva`,
      languages: {
        ...Object.fromEntries(LOCALES.map((l) => [l, `${SITE_URL}/${l}/nueva`])),
        // Pisa el del layout: sin esta línea la página queda sin `x-default` y
        // a quien no le calza ninguno de los tres idiomas Google le elige uno.
        "x-default": `${SITE_URL}/${DEFAULT_LOCALE}/nueva`,
      },
    },
    openGraph: {
      type: "website",
      siteName: "ASTRA",
      locale,
      title: `${t.seoTitle} · ASTRA`,
      description: t.seoDescription,
      url: `${SITE_URL}/${locale}/nueva`,
    },
    twitter: {
      card: "summary_large_image",
      title: `${t.seoTitle} · ASTRA`,
      description: t.seoDescription,
    },
  };
}

export default async function NewChartPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const dict = getDict(locale);
  const signedIn = await haySesion();
  const t = dict.newChart;

  return (
    <>
      <Nav locale={locale} dict={dict} path="/nueva" signedIn={signedIn} showExample={!signedIn} />

      <main className="docFrame formFrame">
        <section className="formHead">
          <h1 className="display formTitle">{signedIn ? t.title : t.seoTitle}</h1>
          <p className="formLede">{signedIn ? t.lede : t.seoIntro}</p>
        </section>

        <NewChartForm locale={locale} dict={dict} signedIn={signedIn} />

        {/* El texto va DEBAJO del formulario y sólo para quien no entró: es lo
            que hace la página indexable —un formulario solo no es contenido
            para nadie— sin empujar hacia abajo lo que se vino a hacer. Quien
            ya tiene sesión no lo necesita y no lo ve. */}
        {!signedIn && (
          <section className="formSeo">
            <h2 className="seoTitle">{t.seoQueEs}</h2>
            <p className="seoBody">{t.seoQueEsBody}</p>
            <h2 className="seoTitle">{t.seoHora}</h2>
            <p className="seoBody">{t.seoHoraBody}</p>
            <h2 className="seoTitle">{t.seoGratis}</h2>
            <p className="seoBody">{t.seoGratisBody}</p>
          </section>
        )}
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
