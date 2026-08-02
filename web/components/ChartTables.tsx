import { signOf } from "@/lib/ephemeris";
import { ASPECT_GLYPHS, ASPECT_NAMES, PLANET_NAME_BY_KEY, type Dict, type Locale } from "@/lib/i18n";
import type { ApiChart } from "@/lib/chart";

// Casas y aspectos, plegados. Son las otras dos tablas que muestra la app; acá
// arrancan cerradas porque la carta ya entra con la rueda y las posiciones, y
// quien quiere el detalle lo abre. Se usa <details>, que despliega sin
// JavaScript y ya viene navegable con teclado.

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const HOUSE_ORDER = [
  "First_House", "Second_House", "Third_House", "Fourth_House",
  "Fifth_House", "Sixth_House", "Seventh_House", "Eighth_House",
  "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
];

function degreeLabel(lon: number): string {
  const inSign = lon % 30;
  const deg = Math.floor(inSign);
  const min = Math.floor((inSign - deg) * 60);
  return `${String(deg).padStart(2, "0")}°${String(min).padStart(2, "0")}′`;
}

export function ChartTables({
  chart,
  locale,
  dict,
}: {
  chart: ApiChart;
  locale: Locale;
  dict: Dict;
}) {
  const { houses, aspects } = chart.data;
  const nombres = PLANET_NAME_BY_KEY[locale];
  const aspectos = ASPECT_NAMES[locale];

  return (
    <div className="foldouts">
      {houses && houses.length > 0 && (
        <details className="foldout">
          <summary className="foldoutHead">{dict.chart.houses}</summary>
          <table className="chartTable">
            <tbody>
              {HOUSE_ORDER.map((name, i) => {
                const casa = houses.find((h) => h.name === name);
                if (!casa) return null;
                return (
                  <tr key={name}>
                    <td className="cellGlyph">{ROMAN[i]}</td>
                    <td>
                      {degreeLabel(casa.abs_pos)} {signOf(casa.abs_pos)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      )}

      {aspects.length > 0 && (
        <details className="foldout">
          <summary className="foldoutHead">
            {dict.chart.aspects} <span className="foldoutCount">{aspects.length}</span>
          </summary>
          <table className="chartTable">
            <thead>
              <tr>
                <th>{dict.chart.aspectColumns.pair}</th>
                <th>{dict.chart.aspectColumns.aspect}</th>
                <th className="cellRight">{dict.chart.aspectColumns.orb}</th>
              </tr>
            </thead>
            <tbody>
              {aspects.map((a) => (
                <tr key={`${a.p1}-${a.p2}-${a.aspect}`}>
                  <td className="cellBody">
                    {nombres[a.p1] ?? a.p1.replace(/_/g, " ")} ·{" "}
                    {nombres[a.p2] ?? a.p2.replace(/_/g, " ")}
                  </td>
                  <td>
                    <span className="aspectGlyph">{ASPECT_GLYPHS[a.aspect] ?? "·"}</span>{" "}
                    {aspectos[a.aspect] ?? a.aspect}
                  </td>
                  {/* El orbe es la distancia al ángulo exacto: cuanto menor, más fuerte. */}
                  <td className="cellRight">{a.orbit.toFixed(1)}°</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
