import { buildMatrix } from "astra-wheel";

import {
  ASPECT_ANGLE,
  ASPECT_GLYPHS,
  ASPECT_MEANING,
  ASPECT_NAMES,
  PLANET_GLYPHS,
  PLANET_NAME_BY_KEY,
  type Locale,
} from "@/lib/i18n";

/** Los ejes en palabras, para la ficha. */
const AXIS_NAME: Record<Locale, Record<string, string>> = {
  es: { Ascendant: "Ascendente", Medium_Coeli: "Medio Cielo", Descendant: "Descendente", Imum_Coeli: "Fondo del Cielo" },
  en: { Ascendant: "Ascendant", Medium_Coeli: "Midheaven", Descendant: "Descendant", Imum_Coeli: "Imum Coeli" },
  pt: { Ascendant: "Ascendente", Medium_Coeli: "Meio do Céu", Descendant: "Descendente", Imum_Coeli: "Fundo do Céu" },
};

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
  orbeLabel,
  glosarioTitulo,
  glosarioCuenta,
  verAspectos,
}: {
  bodies: string[];
  aspects: { a: string; b: string; type: string; orb: number }[];
  locale: Locale;
  titulo: string;
  /** Cómo se llama al orbe en la ficha: "orbe", "orb". */
  orbeLabel: string;
  /** Título del glosario: "Qué significa cada aspecto". */
  glosarioTitulo: string;
  /** Cuántos hay de ese tipo en esta carta. Lleva `{n}`. */
  glosarioCuenta: string;
  /** El desplegable de la lista, como frase: «Ver los {n} aspectos». */
  verAspectos: string;
}) {
  const participantes = new Set(aspects.flatMap((a) => [a.a, a.b]));
  const order = [
    ...bodies,
    ...Object.keys(ANGLE_LABEL).filter((n) => participantes.has(n) && !bodies.includes(n)),
  ];
  const { pairs } = buildMatrix(order, aspects);

  const porPar = new Map(pairs.map((p) => [`${p.a}|${p.b}`, p]));
  const nombres = ASPECT_NAMES[locale];
  const cuerpos = PLANET_NAME_BY_KEY[locale];
  const significados = ASPECT_MEANING[locale];

  /** El nombre largo, para la ficha: en un glifo no se aprende nada. */
  const nombrar = (n: string) => cuerpos[n] ?? AXIS_NAME[locale][n] ?? n.replace(/_/g, " ");

  /**
   * Los tipos de aspecto que esta carta tiene, con cuántos hay de cada uno.
   *
   * La glosa de un aspecto habla del TIPO, no del par: "fluye sin esfuerzo" es
   * lo que hace un trígono, sea Sol-Júpiter o Luna-Plutón. Dicha una vez por
   * tipo se lee; repetida en cada uno de los sesenta y dos pares se convierte
   * en relleno. Y la cuenta es lo único de acá que es de esta carta y de
   * ninguna otra: contesta de qué está hecha.
   *
   * El desempate por ángulo no es cosmético: sin él, dos tipos con la misma
   * cuenta salen en el orden en que el Map los recorrió y el HTML cambia entre
   * builds de la misma carta.
   */
  const cuentaPorTipo = new Map<string, number>();
  for (const p of pairs) cuentaPorTipo.set(p.type, (cuentaPorTipo.get(p.type) ?? 0) + 1);
  const glosario = [...cuentaPorTipo.entries()]
    .filter(([type]) => significados[type])
    .map(([type, cuenta]) => ({ type, cuenta }))
    .sort(
      (x, y) =>
        y.cuenta - x.cuenta || (ASPECT_ANGLE[x.type] ?? 999) - (ASPECT_ANGLE[y.type] ?? 999),
    );

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
                      <span className="matrixMark">{ASPECT_GLYPHS[par.type] ?? "·"}</span>
                      {/* La ficha explica el aspecto: quién con quién, de qué
                          ángulo sale, cuánto se aparta y qué significa. Abre
                          con CSS, sin JavaScript. */}
                      <span className="matrixTip" role="note">
                        <b>
                          {nombrar(col)} {(nombres[par.type] ?? par.type).toLowerCase()} {nombrar(fila)}
                        </b>
                        <span className="matrixTipData">
                          {ASPECT_ANGLE[par.type] != null ? `${ASPECT_ANGLE[par.type]}°` : null}
                          {ASPECT_ANGLE[par.type] != null ? " · " : null}
                          {orbeLabel} {par.orb.toFixed(1)}°
                        </span>
                        {significados[par.type] ? <span>{significados[par.type]}</span> : null}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* El glosario. Va acá, entre la matriz y la lista, porque en pantalla
          angosta —donde la matriz no se dibuja— es lo primero del bloque: qué
          significan antes del detalle de cuáles hay.

          No está plegado a propósito. La glosa vivía sólo en la ficha de la
          matriz, y la ficha necesita `:hover`: en un teléfono, donde la matriz
          además está en `display: none`, las explicaciones no existían. Plegarlo
          las dejaría a un toque de distancia en vez de a ninguno, para ahorrar
          siete líneas. */}
      {glosario.length > 0 ? (
        <div className="aspectGlossary">
          <p className="eyebrow">{glosarioTitulo}</p>
          <dl className="glossaryList">
            {glosario.map(({ type, cuenta }) => (
              <div key={type} className="glossaryItem">
                <dt className="glossaryTerm">
                  <span className="glossaryGlyph">{ASPECT_GLYPHS[type] ?? "·"}</span>
                  <span className="glossaryName">{nombres[type] ?? type}</span>
                  {ASPECT_ANGLE[type] != null ? (
                    <span className="glossaryAngle">{ASPECT_ANGLE[type]}°</span>
                  ) : null}
                  <span className="glossaryCount">
                    {glosarioCuenta.replace("{n}", String(cuenta))}
                  </span>
                </dt>
                <dd className="glossaryMeaning">{significados[type]}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {/* La lista con los orbes. Va plegada porque son decenas de filas: una
          carta típica pasa los sesenta aspectos. En pantalla ancha acompaña a
          la matriz —que muestra el conjunto pero calla los orbes salvo al
          pasar el mouse, de a uno— y en angosta la reemplaza. Se usa
          <details>, que abre sin JavaScript. */}
      <details className="foldout aspectListWrap">
        <summary className="foldoutHead">
          {verAspectos.replace("{n}", String(pairs.length))}
        </summary>
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
