import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/Nav";
import { NatalWheel } from "@/components/NatalWheel";
import { LEGAL_CONTACT } from "@/content/legal";
import { SAMPLE_BIRTH, SAMPLE_CHART } from "@/content/sample-chart";
import { SAMPLE_READING } from "@/content/sample-reading";
import { LOCALES, PLANET_NAME_BY_KEY, getDict, isLocale } from "@/lib/i18n";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://astra.dothecode.com";

const SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const GLYPH: Record<string, string> = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
};

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

  return (
    <>
      <Nav locale={locale} dict={dict} path="/ejemplo" />

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
                  {SAMPLE_CHART.planets.map((planet) => (
                    <tr key={planet.name}>
                      <td className="cellGlyph">{GLYPH[planet.name]}</td>
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

            <p className="eyebrow">{reading.legend.axes}</p>
            <div className="legend">
              <span>ASC {degreeLabel(SAMPLE_CHART.angles.Ascendant)} {SIGNS[Math.floor(SAMPLE_CHART.angles.Ascendant / 30)]}</span>
              <span>MC {degreeLabel(SAMPLE_CHART.angles.Medium_Coeli)} {SIGNS[Math.floor(SAMPLE_CHART.angles.Medium_Coeli / 30)]}</span>
            </div>
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

        <footer className="foot">
          <span>{dict.foot.brand}</span>
          <nav className="footLinks">
            <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
            <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
            <a href={`mailto:${LEGAL_CONTACT}`}>{dict.foot.contact}</a>
          </nav>
        </footer>
      </main>
    </>
  );
}
