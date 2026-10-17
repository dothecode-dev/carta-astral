"use client";

import Link from "next/link";

import { ChartBody } from "@/components/ChartBody";
import { DatosCarta } from "@/components/DatosCarta";
import { Teaser } from "@/components/Teaser";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";

// Lo que ve quien calculó su carta sin tener cuenta. Es la carta entera —la
// misma rueda y las mismas tablas que ve un usuario registrado—, y antes de la
// rueda, lo que ya se puede leer de ella: el teaser y el índice del informe
// (spec 2026-10-17). Hasta el 17-10-2026 acá se ofrecía una lectura breve por
// IA gratis; se apagó porque costaba por visita y no llevaba a ninguna compra.
// El código de esa lectura sigue en el repo (`useLecturaAnonima`), sin usarse
// desde esta pantalla.

export function CartaPreview({
  carta,
  dict,
  locale,
  onVolver,
  precio,
  onComprar,
  comprando,
  errorCompra,
}: {
  carta: CartaDibujable;
  dict: Dict;
  locale: Locale;
  onVolver: () => void;
  /** El precio del informe, ya formateado por `lib/catalogo`. `null` si el
   *  catálogo no respondió: sin precio no se ofrece comprar. */
  precio: string | null;
  onComprar: () => void | Promise<void>;
  comprando: boolean;
  errorCompra: string | null;
}) {
  const t = dict.newChart;

  return (
    <section className="previewCarta">
      <header className="previewHead">
        <h2 className="display previewTitle">{t.previewTitle}</h2>
        <p className="previewLede">{t.previewLede}</p>
      </header>

      {/* Sin teaser (un backend viejo) se muestra todo lo demás. */}
      {carta.teaser && <Teaser teaser={carta.teaser} locale={locale} dict={dict} />}

      {/* La compra va ACÁ, después de ver qué hay en el informe y antes de la
          rueda: es la acción principal de la pantalla. Hasta el 17-10-2026 era
          secundaria (`btnGhost`) porque el principal era la lectura gratis; con
          esa apagada, el único camino que sigue es este. Pagar es entrar: se
          compra sin pasar por /entrar. */}
      {precio && (
        <div className="previewCta">
          {errorCompra && (
            <p className="compraError" role="alert">
              {errorCompra}
            </p>
          )}
          <button
            type="button"
            className="btn btnPrimary"
            disabled={comprando}
            onClick={() => void onComprar()}
          >
            {comprando ? dict.precios.abriendo : t.comprarCta.replace("{precio}", precio)}
          </button>
          {carta.teaser && (
            <p className="fieldNote">
              {t.informeTrae
                .replace("{n}", String(carta.teaser.informe.secciones))
                // "always": en es, ICU no agrupa los números de cuatro cifras
                // (6200) y al lado de pt (6.200) se vería inconsistente.
                .replace("{palabras}", carta.teaser.informe.palabras.toLocaleString(locale, { useGrouping: "always" }))}
            </p>
          )}
          <p className="fieldNote">
            {t.legalAntes}
            <Link href={`/${locale}/legal/terms`}>{t.legalTerminos}</Link>
            {t.legalY}
            <Link href={`/${locale}/legal/privacy`}>{t.legalPrivacidad}</Link>
            {t.legalDespues}
          </p>
        </div>
      )}

      <ChartBody chart={carta} dict={dict} locale={locale} soloRueda />

      <DatosCarta chart={carta} dict={dict} locale={locale} />

      <footer className="previewPie">
        <p className="fieldNote">{precio ? t.previewPrivacidad : t.previewPrivacidadSinCompra}</p>
        <button type="button" className="btn btnGhost" onClick={onVolver}>
          {t.navNew}
        </button>
      </footer>
    </section>
  );
}
