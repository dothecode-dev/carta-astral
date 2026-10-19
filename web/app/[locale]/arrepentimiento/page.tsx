import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ArrepentimientoForm } from "@/components/ArrepentimientoForm";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { haySesion } from "@/lib/session";

// El botón de arrepentimiento (Res. SCI 424/2020): se llega desde el pie de
// todas las páginas y no pide cuenta. Registra el pedido; el reembolso se
// resuelve a mano (mini-spec del 19-10-2026).

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
  return { title: `${getDict(locale).arrepentimiento.titulo} — ASTRA`, robots: { index: false, follow: true } };
}

export default async function ArrepentimientoPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const dict = getDict(locale);
  const t = dict.arrepentimiento;
  const signedIn = await haySesion();

  return (
    <>
      <Nav locale={locale} dict={dict} path="/arrepentimiento" signedIn={signedIn} />
      <main className="docFrame">
        <h1 className="display">{t.titulo}</h1>
        <p>{t.lede}</p>
        <ArrepentimientoForm locale={locale} dict={dict} />
      </main>
      <Footer locale={locale} dict={dict} />
    </>
  );
}
