import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ChartActions } from "@/components/ChartActions";
import { ChartShare } from "@/components/ChartShare";
import { AspectMatrix } from "@/components/AspectMatrix";
import { ChartBody } from "@/components/ChartBody";
import { ChartTables } from "@/components/ChartTables";
import { Nav } from "@/components/Nav";
import { Reading } from "@/components/Reading";
import { ResumenCompleto, type SeccionIndice } from "@/components/ResumenCompleto";
import { type ApiChart, toWheel } from "@/lib/chart";
import type { Derecho } from "@/lib/derechos";
import { INTL_LOCALE, type Locale, getDict, isLocale } from "@/lib/i18n";
import { buildPdfPayload } from "@/lib/pdfPayload";
import { ApiError, RUTA_SESION_EXPIRADA, callApi, getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function ChartPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  if (!isLocale(locale)) notFound();
  if (!(await getSessionToken()))
    redirect(`/${locale}/entrar?next=${encodeURIComponent(`/${locale}/carta/${id}`)}`);

  const dict = getDict(locale);

  let chart: ApiChart;
  try {
    chart = await callApi<ApiChart>(`/api/charts/${id}/`);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect(RUTA_SESION_EXPIRADA(locale));
      // La carta no existe, o es de otra cuenta: para quien mira es lo mismo.
      if (error.status === 404) notFound();
    }
    throw error;
  }

  // Derechos de la cuenta: lectura_breve paga la breve, informe_natal paga
  // el completo. Los botones de abajo los necesitan para saber qué ofrecer.
  let account: { derechos: Derecho[] };
  try {
    account = await callApi<{ derechos: Derecho[] }>(`/api/account/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect(RUTA_SESION_EXPIRADA(locale));
    throw error;
  }

  // La lectura ya escrita en este idioma, si la hay: el completo si está, si
  // no la breve. El GET no genera ni cobra: cuando ninguna existe devuelve
  // 404 y la página muestra los botones.
  const tiersAqui = chart.interpretations[locale] ?? [];
  let reading: { text: string; disclaimer: string } | null = null;
  if (tiersAqui.length > 0) {
    const tier = tiersAqui.includes("largo") ? "largo" : "corto";
    try {
      reading = await callApi(`/api/charts/${id}/interpretation/?lang=${locale}&tier=${tier}`);
    } catch {
      // Si falla, la carta se muestra igual y los botones vuelven a estar.
    }
  }

  // El pie de la lectura breve, con lo que trae el informe completo (RF3).
  // Sólo tiene sentido bajo una lectura ya mostrada, y nunca para quien ya
  // tiene el completo (`tiersAqui` incluye "largo"): no hay nada que
  // venderle. En ese caso `secciones` queda vacío y `ResumenCompleto` no
  // renderiza nada — la decisión de mostrarlo vive acá, no en el componente.
  let secciones: SeccionIndice[] = [];
  if (reading && !tiersAqui.includes("largo")) {
    try {
      secciones = await callApi(`/api/charts/${id}/informe/indice/?lang=${locale}`);
    } catch {
      // Si falla, el pie simplemente no se muestra.
    }
  }

  // Para el PDF con la lectura: la de este idioma si está, y si no cualquiera de
  // las que haya. Traducir una lectura ya escrita no cuesta, pero mientras nadie
  // la pida existe sólo en el idioma en que se generó, y negarle el PDF a quien
  // ya la pagó por estar navegando en otro sería absurdo.
  const readingLang: Locale | null = chart.interpretation_langs.includes(locale)
    ? locale
    : ((chart.interpretation_langs.filter(isLocale)[0] as Locale | undefined) ?? null);

  // Se arma una vez y se ubica según haya lectura o no (ver abajo). El mismo
  // elemento en los dos lugares: duplicarlo sería duplicarle el estado.
  const acciones = (
    <ChartActions
      locale={locale}
      chartId={chart.id}
      interpretations={chart.interpretations}
      enCurso={chart.en_curso}
      derechos={account.derechos}
      timeKnown={chart.birth.time_known}
      dict={dict}
    />
  );

  const wheel = toWheel(chart);
  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${chart.birth.date}T12:00:00Z`));

  return (
    <>
      {/* El path va con el id: si fuera "/cuenta", cambiar de idioma sacaría de
          la carta y llevaría a la lista. */}
      <Nav locale={locale} dict={dict} path={`/carta/${id}`} signedIn showExample={false} />

      <main className="docFrame chartFrame">
        <Link className="backLink" href={`/${locale}/cuenta`}>
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
          {chart.data.flags.bodies_missing && (
            <p className="fieldNote">{dict.chart.incomplete}</p>
          )}
        </section>

        <ChartBody chart={chart} dict={dict} locale={locale} />

        {/* Sin lectura todavía, acá: es lo único que hay para hacer en esta
            página, y más abajo quedaba enterrado bajo las tablas y la matriz de
            aspectos —que en un teléfono son decenas de filas—. Con lectura ya
            escrita se muestra al final (ver abajo): ahí el momento de decidir
            es cuando terminó de leer la breve y está mirando el índice de lo
            que se pierde. */}
        {!reading && acciones}

        <ChartTables chart={chart} dict={dict} />

        {chart.data.aspects.length > 0 && (
          <AspectMatrix
            bodies={chart.data.placements.map((p) => p.name)}
            aspects={chart.data.aspects.map((a) => ({
              a: a.p1,
              b: a.p2,
              type: a.aspect,
              orb: a.orbit,
            }))}
            locale={locale}
            titulo={dict.chart.aspects}
            orbeLabel={dict.chart.aspectColumns.orb}
          />
        )}

        {reading && (
          <section className="reading">
            <p className="eyebrow">{dict.chart.reading}</p>
            <Reading texto={reading.text} />
            <p className="disclaimer">{reading.disclaimer}</p>
          </section>
        )}

        <ResumenCompleto secciones={secciones} dict={dict} />

        {reading && acciones}

        {/* Al final de todo: llevarse la carta es lo que se hace DESPUÉS de
            leerla. En el medio partía la página en dos —tablas, botones,
            lectura— y ofrecía descargar un texto que todavía no se había leído.
            El payload del PDF se arma acá, en el servidor: es la misma tabla
            que ya se calculó arriba, con los nombres traducidos de este idioma. */}
        <ChartShare
          chartId={chart.id}
          payload={buildPdfPayload(chart, locale, dict)}
          wheel={wheel}
          readingLang={readingLang}
          dict={dict}
          locale={locale}
        />
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
