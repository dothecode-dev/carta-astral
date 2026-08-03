import { buildMatrix } from "astra-wheel";

import { ASPECT_GLYPHS, ASPECT_NAMES, PLANET_GLYPHS, type Locale } from "@/lib/i18n";

/** Los ejes se rotulan con letras, no con glifo: no tienen uno de uso corriente. */
const ANGLE_LABEL: Record<string, string> = {
  Ascendant: "AC",
  Medium_Coeli: "MC",
  Descendant: "DC",
  Imum_Coeli: "IC",
};

/** Cuadratura y oposición tensan; trígono y sextil fluyen. El resto, ni una cosa ni otra. */
const HARD = new Set(["square", "opposition"]);
const SOFT = new Set(["trine", "sextile"]);

function rotulo(nombre: string): string {
  return PLANET_GLYPHS[nombre] ?? ANGLE_LABEL[nombre] ?? nombre;
}

/**
 * Los aspectos de la carta.
 *
 * En pantalla ancha, la matriz triangular de las cartas impresas: cada cruce
 * dice qué aspecto hay entre esos dos cuerpos. En pantalla angosta no entra
 * —dieciocho columnas necesitan más de 600px— y se muestra la lista, que
 * además dice el orbe y se lee sin saber leer una matriz.
 *
 * Los pares los arma `astra-wheel`, el mismo paquete que dibuja la rueda: acá
 * no se decide qué va en cada cruce, sólo cómo se ve.
 */
export function AspectMatrix({
  bodies,
  aspects,
  locale,
  titulo,
}: {
  bodies: string[];
  aspects: { a: string; b: string; type: string; orb: number }[];
  locale: Locale;
  titulo: string;
}) {
  const participantes = new Set(aspects.flatMap((a) => [a.a, a.b]));
  const order = [
    ...bodies,
    ...Object.keys(ANGLE_LABEL).filter((n) => participantes.has(n) && !bodies.includes(n)),
  ];
  const { pairs } = buildMatrix(order, aspects);

  const porPar = new Map(pairs.map((p) => [`${p.a}|${p.b}`, p]));
  const nombres = ASPECT_NAMES[locale];

  return (
    <section className="aspects">
      <p className="eyebrow aspectsTitle">{titulo}</p>

      {/* Matriz: sólo en pantalla ancha. */}
      <div className="matrixWrap">
        <table className="aspectMatrix">
          <tbody>
            <tr>
              <td className="matrixCorner" />
              {order.slice(0, -1).map((n) => (
                <th key={n} scope="col" className="matrixHead">
                  {rotulo(n)}
                </th>
              ))}
            </tr>
            {order.slice(1).map((fila, i) => (
              <tr key={fila}>
                <th scope="row" className="matrixHead">
                  {rotulo(fila)}
                </th>
                {order.slice(0, -1).map((col, j) => {
                  if (j > i) return <td key={col} className="matrixVoid" />;
                  const par = porPar.get(`${col}|${fila}`) ?? porPar.get(`${fila}|${col}`);
                  if (!par) return <td key={col} className="matrixCell" />;
                  const clase = HARD.has(par.type)
                    ? "matrixHard"
                    : SOFT.has(par.type)
                      ? "matrixSoft"
                      : "matrixOther";
                  return (
                    <td key={col} className={`matrixCell ${clase}`}>
                      <abbr title={`${nombres[par.type] ?? par.type} · ${par.orb.toFixed(1)}°`}>
                        {ASPECT_GLYPHS[par.type] ?? "·"}
                      </abbr>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Lista: sólo en pantalla angosta. Dice el orbe, que la matriz calla.
          Va plegada porque son decenas de filas: una carta típica tiene más de
          sesenta aspectos, y desplegadas dejan la página interminable en un
          teléfono. Se usa <details>, que abre sin JavaScript. */}
      <details className="foldout aspectListWrap">
        <summary className="foldoutHead">{titulo}</summary>
        <table className="chartTable">
          <tbody>
            {pairs.map((p) => (
              <tr key={`${p.a}-${p.b}-${p.type}`}>
                <td className="cellGlyph">{rotulo(p.a)}</td>
                <td className="cellGlyph">{ASPECT_GLYPHS[p.type] ?? "·"}</td>
                <td className="cellGlyph">{rotulo(p.b)}</td>
                <td className="cellBody">{nombres[p.type] ?? p.type}</td>
                <td className="cellRight">{p.orb.toFixed(1)}°</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
