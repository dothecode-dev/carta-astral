"use client";

import { AspectMatrix } from "@/components/AspectMatrix";
import { ChartBody } from "@/components/ChartBody";
import { ChartTables } from "@/components/ChartTables";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";

// Lo que ve quien calculó su carta sin tener cuenta. Es la carta entera —la
// misma rueda y las mismas tablas que ve un usuario registrado—, porque la
// gracia es que vea algo suyo y completo antes de que se le pida nada. Lo
// único que falta es la lectura escrita, que es lo que cuesta plata y lo único
// por lo que acá se pide una cuenta.

export function CartaPreview({
  carta,
  dict,
  locale,
  onPedirLectura,
  onVolver,
}: {
  carta: CartaDibujable;
  dict: Dict;
  locale: Locale;
  onPedirLectura: () => void;
  onVolver: () => void;
}) {
  const t = dict.newChart;

  return (
    <section className="previewCarta">
      <header className="previewHead">
        <h2 className="display previewTitle">{t.previewTitle}</h2>
        <p className="previewLede">{t.previewLede}</p>
      </header>

      <ChartBody chart={carta} dict={dict} locale={locale} />

      {/* La invitación va ACÁ, no al final: abajo quedan las casas y la matriz
          de aspectos, que en un teléfono son decenas de filas, y el momento de
          decidir es cuando acaba de ver su rueda. */}
      <div className="previewCta">
        <button type="button" className="btn btnPrimary" onClick={onPedirLectura}>
          {t.previewCta}
        </button>
        <p className="fieldNote">{t.previewNote}</p>
      </div>

      <ChartTables chart={carta} dict={dict} />

      {carta.data.aspects.length > 0 && (
        <AspectMatrix
          bodies={carta.data.placements.map((p) => p.name)}
          aspects={carta.data.aspects.map((a) => ({
            a: a.p1,
            b: a.p2,
            type: a.aspect,
            orb: a.orbit,
          }))}
          locale={locale}
          titulo={dict.chart.aspects}
          orbeLabel={dict.chart.aspectColumns.orb}
        />
      )}

      <footer className="previewPie">
        <p className="fieldNote">{t.previewPrivacidad}</p>
        <button type="button" className="btn btnGhost" onClick={onVolver}>
          {t.navNew}
        </button>
      </footer>
    </section>
  );
}
