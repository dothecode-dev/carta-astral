import type { FirmaLinea } from "@/lib/chart";
import { type Dict, type Locale, PLANET_NAME_BY_KEY, SIGN_NAMES } from "@/lib/i18n";

/** Las abreviaturas del motor, en el orden del zodíaco: índice en SIGN_NAMES. */
const SIGNO_INDICE: Record<string, number> = {
  Ari: 0, Tau: 1, Gem: 2, Can: 3, Leo: 4, Vir: 5, Lib: 6, Sco: 7, Sag: 8, Cap: 9, Aqu: 10, Pis: 11,
};

/**
 * Sol, Luna y Ascendente en palabras, debajo del nombre. Es lo único de la
 * carta que entiende quien no sabe leer glifos, y lo que lo hace querer leer
 * más: hasta el 06-10-2026 «Sol en Géminis» había que pescarlo en la fila 3
 * de la tabla de posiciones. Las frases vienen del backend, fijas, en los
 * tres idiomas (`api/firma_frases.py`): acá sólo se elige la del idioma.
 */
export function Firma({ firma, dict, locale }: { firma?: FirmaLinea[]; dict: Dict; locale: Locale }) {
  if (!firma || firma.length === 0) return null;
  const nombres = PLANET_NAME_BY_KEY[locale];
  return (
    <dl className="firma">
      {firma.map((linea) => {
        const cuerpo = linea.cuerpo === "Ascendant" ? dict.chart.axisNames.AC : nombres[linea.cuerpo];
        const signo = SIGN_NAMES[locale][SIGNO_INDICE[linea.signo]];
        return (
          <div key={linea.cuerpo} className="firmaLinea">
            <dt className="firmaTitulo">
              {dict.chart.firmaEn.replace("{cuerpo}", cuerpo).replace("{signo}", signo)}
            </dt>
            <dd className="firmaFrase">{linea.frases[locale]}</dd>
          </div>
        );
      })}
    </dl>
  );
}
