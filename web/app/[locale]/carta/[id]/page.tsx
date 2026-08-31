import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ChartActions } from "@/components/ChartActions";
import { ChartShare } from "@/components/ChartShare";
import { AspectMatrix } from "@/components/AspectMatrix";
import { ChartTables } from "@/components/ChartTables";
import { Nav } from "@/components/Nav";
import { NatalWheel } from "@/components/NatalWheel";
import { Reading } from "@/components/Reading";
import { ResumenCompleto, type SeccionIndice } from "@/components/ResumenCompleto";
import { type ApiChart, toWheel } from "@/lib/chart";
import { signOf } from "@/lib/ephemeris";
import { INTL_LOCALE, type Locale, PLANET_NAME_BY_KEY, getDict, isLocale , PLANET_GLYPHS } from "@/lib/i18n";
import { buildPdfPayload } from "@/lib/pdfPayload";
import { ApiError, RUTA_SESION_EXPIRADA, callApi, getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const HOUSE_INDEX: Record<string, number> = {
  First_House: 1, Second_House: 2, Third_House: 3, Fourth_House: 4,
  Fifth_House: 5, Sixth_House: 6, Seventh_House: 7, Eighth_House: 8,
  Ninth_House: 9, Tenth_House: 10, Eleventh_House: 11, Twelfth_House: 12,
};

function degreeLabel(lon: number): string {
  const inSign = lon % 30;
  const deg = Math.floor(inSign);
  const min = Math.floor((inSign - deg) * 60);
  return `${String(deg).padStart(2, "0")}°${String(min).padStart(2, "0")}′`;
}

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function ChartPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  if (!isLocale(locale)) notFound();
  if (!(await getSessionToken())) redirect(`/${locale}/entrar`);

  const dict = getDict(locale);
  const names = PLANET_NAME_BY_KEY[locale];

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

  // Créditos del lote gratis (pagan la breve) y del pago (pagan el completo),
  // por separado: los botones de abajo los necesitan para saber qué ofrecer.
  let account: { free_credits: number; paid_credits: number };
  try {
    account = await callApi<{ free_credits: number; paid_credits: number }>(`/api/account/`);
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

        <div className="chartBody">
          {wheel ? (
            <NatalWheel chart={wheel} alt={dict.chart.back} />
          ) : (
            <div className="emptyCharts">
              <p className="emptyChartsText">
                <strong>{dict.chart.noWheel}</strong>
              </p>
              <p className="emptyChartsText">{dict.chart.noWheelBody}</p>
            </div>
          )}

          <div className="tableBlock">
            <div className="tableWrap">
              <table className="chartTable">
                <thead>
                  <tr>
                    <th colSpan={2}>{dict.chart.columns.body}</th>
                    <th>{dict.chart.columns.position}</th>
                    <th className="cellRight">{dict.chart.columns.house}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {/* Los ejes primero, como en el PDF. DC e IC no se listan:
                      son los opuestos exactos de AC y MC. */}
                  {(chart.data.angles ?? [])
                    .filter((a) => a.name === "Ascendant" || a.name === "Medium_Coeli")
                    .map((a) => (
                      <tr key={a.name}>
                        <td className="cellGlyph">{a.name === "Ascendant" ? "AC" : "MC"}</td>
                        <td className="cellBody">
                          {dict.chart.axisNames[a.name === "Ascendant" ? "AC" : "MC"]}
                        </td>
                        <td>
                          {degreeLabel(a.abs_pos)} {signOf(a.abs_pos)}
                        </td>
                        <td className="cellRight" />
                        <td className="cellRetro" />
                      </tr>
                    ))}
                  {chart.data.placements.map((p) => (
                    <tr key={p.name}>
                      <td className="cellGlyph">{PLANET_GLYPHS[p.name] ?? "·"}</td>
                      <td className="cellBody">{names[p.name] ?? p.name.replace(/_/g, " ")}</td>
                      <td>
                        {degreeLabel(p.abs_pos)} {signOf(p.abs_pos)}
                      </td>
                      <td className="cellRight">
                        {p.house ? ROMAN[HOUSE_INDEX[p.house] - 1] : "—"}
                      </td>
                      <td className="cellRetro">{p.retrograde ? "℞" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

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

        <ChartActions
          locale={locale}
          chartId={chart.id}
          interpretations={chart.interpretations}
          freeCredits={account.free_credits}
          paidCredits={account.paid_credits}
          timeKnown={chart.birth.time_known}
          dict={dict}
        />

        {/* El payload del PDF se arma acá, en el servidor: es la misma tabla que
            ya se calculó arriba, con los nombres traducidos de este idioma. */}
        <ChartShare
          chartId={chart.id}
          payload={buildPdfPayload(chart, locale, dict)}
          wheel={wheel}
          readingLang={readingLang}
          dict={dict}
          locale={locale}
        />

        {reading && (
          <section className="reading">
            <p className="eyebrow">{dict.chart.reading}</p>
            <Reading texto={reading.text} />
            <p className="disclaimer">{reading.disclaimer}</p>
          </section>
        )}

        <ResumenCompleto secciones={secciones} dict={dict} />

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
