import { signOf } from "@/lib/ephemeris";
import { type Dict } from "@/lib/i18n";
import type { CartaDibujable } from "@/lib/chart";

// Las casas, plegadas. Arranca cerrada porque la carta ya entra con la rueda y
// las posiciones, y quien quiere el detalle lo abre. Se usa <details>, que
// despliega sin JavaScript y ya viene navegable con teclado.
//
// Los aspectos salieron de acá el 2026-08-03: los muestra <AspectMatrix>, que
// en pantalla ancha dibuja la matriz triangular y en angosta la misma lista.

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

export function ChartTables({ chart, dict }: { chart: CartaDibujable; dict: Dict }) {
  const { houses } = chart.data;

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

    </div>
  );
}
