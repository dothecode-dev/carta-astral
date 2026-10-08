import type { ReactNode } from "react";

import { AspectMatrix } from "@/components/AspectMatrix";
import { ChartTables } from "@/components/ChartTables";
import { TablaPosiciones } from "@/components/TablaPosiciones";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";

/** Posiciones, casas y aspectos, plegados: son datos de astrólogo. Quien
 *  llega por «carta natal gratis» quiere la rueda y la firma; esto lo abre
 *  quien ya sabe qué busca. `<details>` abre sin JavaScript. */
export function DatosCarta({
  chart,
  dict,
  locale,
  children,
}: {
  chart: CartaDibujable;
  dict: Dict;
  locale: Locale;
  /** Ajustes de la carta que viven junto a sus datos (p. ej. el trato). */
  children?: ReactNode;
}) {
  return (
    <details className="foldout datosCarta">
      <summary className="foldoutHead">{dict.chart.verDatos}</summary>
      <div className="datosCartaCuerpo">
        {children}
        <TablaPosiciones chart={chart} dict={dict} locale={locale} />
        <ChartTables chart={chart} dict={dict} locale={locale} />
        {chart.data.aspects.length > 0 && (
          <AspectMatrix
            bodies={chart.data.placements.map((p) => p.name)}
            aspects={chart.data.aspects.map((a) => ({ a: a.p1, b: a.p2, type: a.aspect, orb: a.orbit }))}
            locale={locale}
            titulo={dict.chart.aspects}
            orbeLabel={dict.chart.aspectColumns.orb}
            glosarioTitulo={dict.chart.aspectGlossary}
            glosarioCuenta={dict.chart.aspectGlossaryCount}
            verAspectos={dict.chart.verAspectos}
          />
        )}
      </div>
    </details>
  );
}
