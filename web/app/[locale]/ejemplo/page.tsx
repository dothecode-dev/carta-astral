import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/Nav";
import { AspectMatrix } from "@/components/AspectMatrix";
import { NatalWheel } from "@/components/NatalWheel";
import { SAMPLE_BIRTH, SAMPLE_CHART } from "@/content/sample-chart";
import { SAMPLE_READING } from "@/content/sample-reading";
import { LOCALES, PLANET_NAME_BY_KEY, getDict, isLocale , PLANET_GLYPHS } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { Footer } from "@/components/Footer";
import { haySesion } from "@/lib/session";

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const HOUSE_INDEX: Record<string, number> = {
  First_House: 1, Second_House: 2, Third_House: 3, Fourth_House: 4,
  Fifth_House: 5, Sixth_House: 6, Seventh_House: 7, Eighth_House: 8,
  Ninth_House: 9, Tenth_House: 10, Eleventh_House: 11, Twelfth_House: 12,
};

/** Grados y minutos dentro del signo, como se leen en una carta. */
function degreeLabel(lon: number): string {
  const inSign = lon % 30;
  const deg = Math.floor(inSign);
  const min = Math.floor((inSign - deg) * 60);
  return `${String(deg).padStart(2, "0")}°${String(min).padStart(2, "0")}′`;
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export const dynamicParams = false;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const reading = SAMPLE_READING[locale];
  return {
    metadataBase: new URL(SITE_URL),
    title: `${reading.pageTitle} — ASTRA`,
    alternates: {
      canonical: `/${locale}/ejemplo`,
      languages: Object.fromEntries(LOCALES.map((code) => [code, `/${code}/ejemplo`])),
    },
  };
}

export default async function SampleChartPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const dict = getDict(locale);
  const reading = SAMPLE_READING[locale];
  const names = PLANET_NAME_BY_KEY[locale];

  // El header es el mismo en todo el sitio: sin esto la página se sirve
  // estática y le dice "Entrar" a alguien que ya tiene la sesión abierta.
  // Leer la cookie la vuelve dinámica, que es el precio de reconocer a quien
  // entra — y no toca lo que ve Google, que nunca trae cookie.
  const signedIn = await haySesion();

  return (
    <>
      <Nav locale={locale} dict={dict} path="/ejemplo" signedIn={signedIn} showExample={!signedIn} />

      <main className="docFrame chartFrame">
        <section className="chartHead">
          <p className="eyebrow">{reading.eyebrow}</p>
          <h1 className="display chartName">{SAMPLE_BIRTH.name}</h1>
          <div className="birth">
            <span>
              {SAMPLE_BIRTH.date} · <b>{SAMPLE_BIRTH.time}</b>
            </span>
            <span>{SAMPLE_BIRTH.place}</span>
            <span>{SAMPLE_BIRTH.coords}</span>
            <span>{SAMPLE_BIRTH.system}</span>
          </div>
        </section>

        <div className="chartBody">
          <NatalWheel chart={SAMPLE_CHART} alt={reading.wheelAlt} />

          <div className="tableBlock">
            <div className="tableWrap">
              <table className="chartTable">
                <thead>
                  <tr>
                    <th colSpan={2}>{reading.columns.body}</th>
                    <th>{reading.columns.position}</th>
                    <th className="cellRight">{reading.columns.house}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {/* Los ejes primero, como en el PDF. DC e IC no se listan:
                      son los opuestos exactos de AC y MC. */}
                  {([["AC", SAMPLE_CHART.angles.Ascendant], ["MC", SAMPLE_CHART.angles.Medium_Coeli]] as const).map(
                    ([sigla, lon]) => (
                      <tr key={sigla}>
                        <td className="cellGlyph">{sigla}</td>
                        <td className="cellBody">{dict.chart.axisNames[sigla]}</td>
                        <td>
                          {degreeLabel(lon)} {SIGNS[Math.floor(lon / 30)]}
                        </td>
                        <td className="cellRight" />
                        <td className="cellRetro" />
                      </tr>
                    ),
                  )}
                  {SAMPLE_CHART.planets.map((planet) => (
                    <tr key={planet.name}>
                      <td className="cellGlyph">{PLANET_GLYPHS[planet.name]}</td>
                      <td className="cellBody">{names[planet.name] ?? planet.name}</td>
                      <td>
                        {degreeLabel(planet.lon)} {SIGNS[Math.floor(planet.lon / 30)]}
                      </td>
                      <td className="cellRight">{ROMAN[HOUSE_INDEX[planet.house] - 1]}</td>
                      <td className="cellRetro">{planet.retro ? "℞" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="legend">
              <span className="legendSoft">
                <i /> {reading.legend.soft}
              </span>
              <span className="legendHard">
                <i /> {reading.legend.hard}
              </span>
            </div>

            <AspectMatrix
              bodies={SAMPLE_CHART.planets.map((p) => p.name)}
              aspects={SAMPLE_CHART.aspects}
              locale={locale}
              titulo={dict.chart.aspects}
            orbeLabel={dict.chart.aspectColumns.orb}
            />
          </div>
        </div>

        <section className="reading">
          <p className="readingOpen">{reading.opening}</p>

          {reading.passages.map((passage) => (
            <article className="passage" key={passage.source}>
              <p className="passageSource">{passage.source}</p>
              {passage.paragraphs.map((text, i) => (
                <p key={i}>{text}</p>
              ))}
            </article>
          ))}
        </section>

        <div className="close">
          <div className="closeCopy">
            <h2 className="closeTitle">{reading.closing.title}</h2>
            <p className="closeNote">{reading.closing.note}</p>
          </div>
          <Link className="btn btnPrimary" href={`/${locale}#descargar`}>
            {reading.closing.cta}
          </Link>
        </div>

        <p className="disclaimer">{reading.disclaimer}</p>
        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
