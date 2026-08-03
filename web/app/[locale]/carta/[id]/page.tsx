import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ChartActions } from "@/components/ChartActions";
import { AspectMatrix } from "@/components/AspectMatrix";
import { ChartTables } from "@/components/ChartTables";
import { Nav } from "@/components/Nav";
import { NatalWheel } from "@/components/NatalWheel";
import { type ApiChart, toWheel } from "@/lib/chart";
import { signOf } from "@/lib/ephemeris";
import { INTL_LOCALE, PLANET_NAME_BY_KEY, getDict, isLocale , PLANET_GLYPHS } from "@/lib/i18n";
import { ApiError, callApi, getSessionToken } from "@/lib/session";
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
      if (error.status === 401) redirect(`/${locale}/entrar`);
      // La carta no existe, o es de otra cuenta: para quien mira es lo mismo.
      if (error.status === 404) notFound();
    }
    throw error;
  }

  // La lectura ya escrita, si la hay. El GET no genera ni cobra: cuando todavía
  // no existe devuelve 404 y la página muestra el botón.
  let reading: { text: string; disclaimer: string } | null = null;
  if (chart.interpretation_langs.includes(locale)) {
    try {
      reading = await callApi(`/api/charts/${id}/interpretation/?lang=${locale}`);
    } catch {
      // Si falla, la carta se muestra igual y el botón vuelve a estar.
    }
  }

  const wheel = toWheel(chart);
  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${chart.birth.date}T12:00:00Z`));

  return (
    <>
      <Nav locale={locale} dict={dict} path="/cuenta" signedIn showExample={false} />

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
          />
        )}

        <ChartActions
          locale={locale}
          chartId={chart.id}
          langs={chart.interpretation_langs}
          dict={dict}
        />

        {reading && (
          <section className="reading">
            <p className="eyebrow">{dict.chart.reading}</p>
            {reading.text.split(/\n{2,}/).map((parrafo, i) => (
              <p key={i} className="readingParagraph">
                {parrafo.trim()}
              </p>
            ))}
            <p className="disclaimer">{reading.disclaimer}</p>
          </section>
        )}

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
