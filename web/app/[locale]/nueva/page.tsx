import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { Nav } from "@/components/Nav";
import { NewChartForm } from "@/components/NewChartForm";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";

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
  return { title: `${getDict(locale).newChart.title} — ASTRA`, robots: { index: false } };
}

export default async function NewChartPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  // Calcular una carta la guarda en una cuenta: sin sesión no hay dónde. Se
  // vuelve acá al entrar: el CTA principal de la home termina en esta página,
  // y mandar a la cuenta a quien venía a calcular su carta lo obligaba a
  // empezar de nuevo sin haberle avisado nunca que hacía falta una cuenta.
  if (!(await getSessionToken()))
    redirect(`/${locale}/entrar?next=${encodeURIComponent(`/${locale}/nueva`)}`);

  const dict = getDict(locale);

  return (
    <>
      <Nav locale={locale} dict={dict} path="/nueva" signedIn showExample={false} />

      <main className="docFrame formFrame">
        <section className="formHead">
          <h1 className="display formTitle">{dict.newChart.title}</h1>
          <p className="formLede">{dict.newChart.lede}</p>
        </section>

        <NewChartForm locale={locale} dict={dict} />

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
