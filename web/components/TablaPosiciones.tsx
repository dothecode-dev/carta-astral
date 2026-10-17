import type { CartaDibujable } from "@/lib/chart";
import { positionLabel } from "@/lib/ephemeris";
import { type Dict, KERYKEION_SIGNS, type Locale, PLANET_GLYPHS, PLANET_NAME_BY_KEY, SIGN_NAMES, SIGNS } from "@/lib/i18n";

// La tabla de posiciones: ejes y cuerpos con grado, signo y casa. Vivía dentro
// de ChartBody junto a la rueda; el 06-10-2026 se separó para poder plegarla
// con el resto de los datos (DatosCarta) y dejar la rueda sola arriba.

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const HOUSE_INDEX: Record<string, number> = {
  First_House: 1, Second_House: 2, Third_House: 3, Fourth_House: 4,
  Fifth_House: 5, Sixth_House: 6, Seventh_House: 7, Eighth_House: 8,
  Ninth_House: 9, Tenth_House: 10, Eleventh_House: 11, Twelfth_House: 12,
};

/** La posición de un cuerpo para la tabla. La Luna de una carta sin hora que
 *  cambia de signo ese día no tiene un grado ni un signo que afirmar: se
 *  muestran los dos signos posibles, como en el teaser y la firma. */
function posicion(p: CartaDibujable["data"]["placements"][number], chart: CartaDibujable, dict: Dict, locale: Locale): string {
  const flags = chart.data.flags;
  if (p.name !== "Moon" || !flags.moon_sign_uncertain) return positionLabel(p.abs_pos, locale);
  const opciones = (flags.moon_sign_options ?? []).map((s) => KERYKEION_SIGNS.indexOf(s));
  if (opciones.length !== 2 || opciones.some((i) => i < 0)) return dict.chart.lunaIncierta;
  const [a, b] = opciones.map((i) => `${SIGNS[i]} ${SIGN_NAMES[locale][i]}`);
  return dict.chart.lunaDudosa.replace("{a}", a).replace("{b}", b);
}

export function TablaPosiciones({
  chart,
  dict,
  locale,
}: {
  chart: CartaDibujable;
  dict: Dict;
  locale: Locale;
}) {
  const names = PLANET_NAME_BY_KEY[locale];

  return (
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
                    {positionLabel(a.abs_pos, locale)}
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
                  {posicion(p, chart, dict, locale)}
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
  );
}
