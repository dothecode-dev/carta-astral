"use client";

import Link from "next/link";

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
  precio,
  onComprar,
  comprando,
  errorCompra,
}: {
  carta: CartaDibujable;
  dict: Dict;
  locale: Locale;
  onPedirLectura: () => void;
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

        {/* Pagar es entrar: el informe se compra acá mismo, sin pasar por
            /entrar. Es secundario a propósito: la lectura gratis sigue siendo
            lo primero que se ofrece. */}
        {precio && (
          <>
            {errorCompra && (
              <p className="compraError" role="alert">
                {errorCompra}
              </p>
            )}
            <button
              type="button"
              className="btn btnGhost"
              disabled={comprando}
              onClick={() => void onComprar()}
            >
              {comprando ? dict.precios.abriendo : t.comprarCta.replace("{precio}", precio)}
            </button>
            <p className="fieldNote">
              {t.legalAntes}
              <Link href={`/${locale}/legal/terms`}>{t.legalTerminos}</Link>
              {t.legalY}
              <Link href={`/${locale}/legal/privacy`}>{t.legalPrivacidad}</Link>
              {t.legalDespues}
            </p>
          </>
        )}
      </div>

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
