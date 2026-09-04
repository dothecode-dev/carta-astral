import { NatalWheel } from "@/components/NatalWheel";
import { type CartaDibujable, toWheel } from "@/lib/chart";
import { signOf } from "@/lib/ephemeris";
import { type Dict, type Locale, PLANET_GLYPHS, PLANET_NAME_BY_KEY } from "@/lib/i18n";

// La rueda y la tabla de posiciones, que son lo que hace que una carta se vea
// como una carta. Vivían copiadas dentro de `/carta/[id]`; el 04-09-2026
// apareció el tercer lugar que las necesitaba —el preview de quien todavía no
// tiene cuenta— y copiarlas una vez más garantizaba que las tres se fueran
// separando.
//
// Recibe `CartaDibujable` y no `ApiChart` a propósito: para dibujar no hace
// falta que la carta exista como fila, y ese es justamente el caso del preview.

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

export function ChartBody({
  chart,
  dict,
  locale,
}: {
  chart: CartaDibujable;
  dict: Dict;
  locale: Locale;
}) {
  const wheel = toWheel(chart);
  const names = PLANET_NAME_BY_KEY[locale];

  return (
    <div className="chartBody">
      {wheel ? (
        <NatalWheel chart={wheel} alt={dict.chart.back} />
      ) : (
        // Sin hora no hay Ascendente ni casas, así que no hay rueda que
        // dibujar: se dice por qué en vez de dejar un hueco.
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
  );
}
