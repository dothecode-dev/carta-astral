import Link from "next/link";

import { HoraLocal, ZonaDeLasHoras } from "@/components/HoraLocal";
import { SkyWheel } from "@/components/SkyWheel";
import { CIELO } from "@/content/cielo";
import { formatDegree, positionLabel, positions, signName, type Positions } from "@/lib/ephemeris";
import { instanteUtc } from "@/lib/instante";
import { PLANET_GLYPHS, PLANET_NAME_BY_KEY, SIGN_NAMES, type Locale } from "@/lib/i18n";
import type { Moon, Sky, SkyBody } from "@/lib/sky";

/** El orden de la rueda, en inglés: es lo que devuelve el backend. */
const RESPALDO: { name: string; key: keyof Positions }[] = [
  { name: "Sun", key: "sun" }, { name: "Moon", key: "moon" },
  { name: "Mercury", key: "mercury" }, { name: "Venus", key: "venus" },
  { name: "Mars", key: "mars" }, { name: "Jupiter", key: "jupiter" },
  { name: "Saturn", key: "saturn" }, { name: "Uranus", key: "uranus" },
  { name: "Neptune", key: "neptune" },
];

/** Los cuerpos a listar. Sin backend salen del cálculo local de la portada:
 *  sin Plutón y sin saber cuáles están retrógrados, que es lo único que ese
 *  cálculo no da. `null` en `retrograde` quiere decir «no se sabe». */
function cuerpos(sky: Sky | null, ahora: Date): (Omit<SkyBody, "retrograde"> & { retrograde: boolean | null })[] {
  if (sky) return sky.bodies;
  const pos = positions(ahora);
  return RESPALDO.map(({ name, key }) => ({ name, longitude: pos[key], retrograde: null }));
}

/** El cuerpo de «el cielo de hoy»: todo lo que importa sale en el HTML del
 *  servidor, que es lo que lee un buscador. Lo único que cambia en el
 *  navegador es la zona de las horas. */
export function CieloHoy({
  locale,
  sky,
  moon,
  ahora,
}: {
  locale: Locale;
  sky: Sky | null;
  moon: Moon | null;
  ahora: Date;
}) {
  const t = CIELO[locale];
  const nombres = PLANET_NAME_BY_KEY[locale];
  const lista = cuerpos(sky, ahora);
  const luna = lista.find((b) => b.name === "Moon");
  const signoLuna = luna ? Math.floor(luna.longitude / 30) : null;
  const retrogrados = lista.filter((b) => b.retrograde);
  const momento = sky?.moment ?? ahora.toISOString();

  return (
    <>
      <section className="chartHead">
        <p className="eyebrow">{t.eyebrow}</p>
        <h1 className="display chartName">{t.title}</h1>
        <div className="birth">
          <span>
            {t.computedAt} <HoraLocal iso={momento} utc={instanteUtc(momento, locale)} locale={locale} />
          </span>
        </div>
        <p className="cieloLede">{t.lede}</p>
      </section>

      {luna && signoLuna !== null && (
        <section className="cieloBloque">
          <h2 className="closeTitle">{t.moonHeading}</h2>
          <p className="readingOpen">
            {t.moonIn(signName(luna.longitude, locale), formatDegree(luna.longitude))}
            {moon && (
              <>
                {" "}
                <b>{t.phaseNames[moon.phase]}</b>
                {t.illumination(moon.illumination)}
              </>
            )}
          </p>
          {moon && (
            <p>
              {t.entersSign(SIGN_NAMES[locale][moon.nextSignIndex])}{" "}
              <HoraLocal iso={moon.nextSignMoment} utc={instanteUtc(moon.nextSignMoment, locale)} locale={locale} />
            </p>
          )}
          <p>{t.moonSigns[signoLuna]}</p>
        </section>
      )}

      {moon && (
        <section className="cieloBloque">
          <h2 className="closeTitle">{t.nextPhasesHeading}</h2>
          <ul className="cieloFases">
            {moon.nextPhases.map((f) => (
              <li key={f.phase}>
                <span>{t.phaseNames[f.phase]}</span>
                <HoraLocal iso={f.moment} utc={instanteUtc(f.moment, locale)} locale={locale} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="chartBody">
        <SkyWheel alt={t.wheelAlt} initial={sky?.positions ?? null} />

        <div className="tableBlock">
          <h2 className="closeTitle">{t.tableHeading}</h2>
          <div className="tableWrap">
            <table className="chartTable">
              <thead>
                <tr>
                  <th colSpan={2}>{t.columns.body}</th>
                  <th>{t.columns.position}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lista.map((b) => (
                  <tr key={b.name}>
                    <td className="cellGlyph">{PLANET_GLYPHS[b.name]}</td>
                    <td className="cellBody">{nombres[b.name] ?? b.name}</td>
                    <td>{positionLabel(b.longitude, locale)}</td>
                    <td className="cellRetro">
                      {b.retrograde ? <abbr title={t.retroMark}>℞</abbr> : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {sky && (
        <section className="cieloBloque">
          <h2 className="closeTitle">{t.retroHeading}</h2>
          {retrogrados.length === 0 ? (
            <p>{t.retroNone}</p>
          ) : (
            <p>
              {t.retroSome}{" "}
              {retrogrados
                .map((b) => `${nombres[b.name] ?? b.name} (${signName(b.longitude, locale)})`)
                .join(", ")}
              .
            </p>
          )}
          <p>{t.retroExplain}</p>
        </section>
      )}

      <ZonaDeLasHoras utc={t.timesInUtc} local={t.timesLocal} />

      <div className="close">
        <div className="closeCopy">
          <h2 className="closeTitle">{t.closing.title}</h2>
          <p className="closeNote">{t.closing.note}</p>
        </div>
        <Link className="btn btnPrimary" href={`/${locale}/nueva`}>
          {t.closing.cta}
        </Link>
      </div>
    </>
  );
}
