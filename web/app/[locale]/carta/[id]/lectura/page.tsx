import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Nav } from "@/components/Nav";
import { type ApiChart } from "@/lib/chart";
import { INTL_LOCALE, getDict, isLocale } from "@/lib/i18n";
import { ApiError, callApi, getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";

type Reading = {
  text: string;
  lang: string;
  disclaimer: string;
  created_at: string;
};

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function ReadingPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  if (!isLocale(locale)) notFound();
  if (!(await getSessionToken())) redirect(`/${locale}/entrar`);

  const dict = getDict(locale);

  let chart: ApiChart;
  let reading: Reading;
  try {
    [chart, reading] = await Promise.all([
      callApi<ApiChart>(`/api/charts/${id}/`),
      // GET: si todavía no está escrita, devuelve 404 y no cobra nada.
      callApi<Reading>(`/api/charts/${id}/interpretation/?lang=${locale}`),
    ]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect(`/${locale}/entrar`);
      // Sin lectura en este idioma: se vuelve a la carta, que tiene el botón.
      if (error.status === 404) redirect(`/${locale}/carta/${id}`);
    }
    throw error;
  }

  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${chart.birth.date}T12:00:00Z`));

  return (
    <>
      <Nav locale={locale} dict={dict} path="/cuenta" signedIn showExample={false} />

      <main className="docFrame chartFrame">
        <Link className="backLink" href={`/${locale}/carta/${id}`}>
          {dict.chart.back}
        </Link>

        <section className="chartHead">
          <h1 className="display chartName">{chart.birth.name || dict.auth.unnamedChart}</h1>
          <div className="birth">
            <span>
              {fecha}
              {chart.birth.time ? ` · ${chart.birth.time}` : ""}
            </span>
            <span>{chart.birth.place_label}</span>
          </div>
        </section>

        <article className="reading">
          {reading.text
            .split(/\n{2,}/)
            .map((parrafo, i) => (
              <p key={i} className="readingParagraph">
                {parrafo.trim()}
              </p>
            ))}
        </article>

        <p className="disclaimer">{reading.disclaimer}</p>

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
