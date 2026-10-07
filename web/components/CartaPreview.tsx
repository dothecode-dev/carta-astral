"use client";

import { ChartBody } from "@/components/ChartBody";
import { DatosCarta } from "@/components/DatosCarta";
import { Firma } from "@/components/Firma";
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
        <Firma firma={carta.firma} dict={dict} locale={locale} />
      </header>

      <ChartBody chart={carta} dict={dict} locale={locale} soloRueda />

      {/* La invitación va ACÁ, apenas vio su rueda, que es el momento de
          decidir. Los datos quedan plegados debajo. */}
      <div className="previewCta">
        <button type="button" className="btn btnPrimary" onClick={onPedirLectura}>
          {t.previewCta}
        </button>
        <p className="fieldNote">{t.previewNote}</p>
      </div>

      <DatosCarta chart={carta} dict={dict} locale={locale} />

      <footer className="previewPie">
        <p className="fieldNote">{t.previewPrivacidad}</p>
        <button type="button" className="btn btnGhost" onClick={onVolver}>
          {t.navNew}
        </button>
      </footer>
    </section>
  );
}
