import { NatalWheel } from "@/components/NatalWheel";
import { type CartaDibujable, toWheel } from "@/lib/chart";
import { TablaPosiciones } from "@/components/TablaPosiciones";
import type { Dict, Locale } from "@/lib/i18n";

// La rueda y la tabla de posiciones, que son lo que hace que una carta se vea
// como una carta. Vivían copiadas dentro de `/carta/[id]`; el 04-09-2026
// apareció el tercer lugar que las necesitaba —el preview de quien todavía no
// tiene cuenta— y copiarlas una vez más garantizaba que las tres se fueran
// separando.
//
// Recibe `CartaDibujable` y no `ApiChart` a propósito: para dibujar no hace
// falta que la carta exista como fila, y ese es justamente el caso del preview.

export function ChartBody({
  chart,
  dict,
  locale,
  soloRueda = false,
}: {
  chart: CartaDibujable;
  dict: Dict;
  locale: Locale;
  /** Sólo la rueda: la tabla va plegada con el resto de los datos (DatosCarta). */
  soloRueda?: boolean;
}) {
  const wheel = toWheel(chart);

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

      {!soloRueda && <TablaPosiciones chart={chart} dict={dict} locale={locale} />}
    </div>
  );
}
