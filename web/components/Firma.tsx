import type { FirmaLinea } from "@/lib/chart";
import { type Dict, KERYKEION_SIGNS, type Locale, PLANET_NAME_BY_KEY, SIGN_NAMES } from "@/lib/i18n";

/** «Sol en Géminis»: el título de una línea de firma, y también de cada bloque
 *  del teaser. `cuerpo` y `signo` son los del motor (`Sun`, `Ascendant`, `Gem`). */
export function tituloCuerpoEnSigno(cuerpo: string, signo: string, dict: Dict, locale: Locale): string {
  const nombre = cuerpo === "Ascendant" ? dict.chart.axisNames.AC : PLANET_NAME_BY_KEY[locale][cuerpo];
  return dict.chart.firmaEn.replace("{cuerpo}", nombre).replace("{signo}", SIGN_NAMES[locale][KERYKEION_SIGNS.indexOf(signo)]);
}

/**
 * Sol, Luna y Ascendente en palabras, debajo del nombre. Es lo único de la
 * carta que entiende quien no sabe leer glifos, y lo que lo hace querer leer
 * más: hasta el 06-10-2026 «Sol en Géminis» había que pescarlo en la fila 3
 * de la tabla de posiciones. Las frases vienen del backend, fijas, en los
 * tres idiomas (`api/firma_frases.py`): acá sólo se elige la del idioma.
 */
export function Firma({ firma, dict, locale }: { firma?: FirmaLinea[]; dict: Dict; locale: Locale }) {
  if (!firma || firma.length === 0) return null;
  return (
    <dl className="firma">
      {firma.map((linea) => {
        return (
          <div key={linea.cuerpo} className="firmaLinea">
            <dt className="firmaTitulo">
              {tituloCuerpoEnSigno(linea.cuerpo, linea.signo, dict, locale)}
            </dt>
            <dd className="firmaFrase">{linea.frases[locale]}</dd>
          </div>
        );
      })}
    </dl>
  );
}
