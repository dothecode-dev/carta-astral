"use client";

import Link from "next/link";

import { ChartBody } from "@/components/ChartBody";
import { DatosCarta } from "@/components/DatosCarta";
import { Firma } from "@/components/Firma";
import { Reading } from "@/components/Reading";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";
import type { EstadoLectura } from "@/components/useLecturaAnonima";

// Lo que ve quien calculó su carta sin tener cuenta. Es la carta entera —la
// misma rueda y las mismas tablas que ve un usuario registrado—, porque la
// gracia es que vea algo suyo y completo antes de que se le pida nada. Lo
// único que falta es la lectura escrita, que es lo que cuesta plata y lo único
// que se escribe acá mismo, sin cuenta, al pedirlo.

export function CartaPreview({
  carta,
  dict,
  locale,
  lectura,
  onPedirLectura,
  onReintentar,
  onVolver,
  precio,
  onComprar,
  comprando,
  errorCompra,
}: {
  carta: CartaDibujable;
  dict: Dict;
  locale: Locale;
  /** La lectura breve sin cuenta: se escribe acá mismo (spec 2026-10-08). */
  lectura: EstadoLectura;
  onPedirLectura: () => void;
  onReintentar: () => void;
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

      {lectura.tipo === "esperando" && (
        <p className="formLede" role="status">{lectura.ocupado ? t.lecturaOcupado : t.lecturaEscribiendo}</p>
      )}
      {lectura.tipo === "lista" && (
        <section className="lecturaAnonima">
          {lectura.lang !== locale && (
            <p className="fieldNote">{t.lecturaOtroIdioma.replace("{idioma}", t.idiomas[lectura.lang])}</p>
          )}
          <Reading texto={lectura.texto} />
          {lectura.disclaimer && <p className="disclaimer">{lectura.disclaimer}</p>}
        </section>
      )}
      {lectura.tipo === "fallida" && (
        <p className="compraError" role="alert">
          {t.lecturaFallida}{" "}
          <button type="button" className="btn btnGhost" onClick={onReintentar}>{t.lecturaReintentar}</button>
        </p>
      )}
      {lectura.tipo === "usada" && <p className="fieldNote" role="status">{t.lecturaUsada}</p>}
      {lectura.tipo === "sin_cupo" && <p className="fieldNote" role="status">{t.lecturaSinCupo}</p>}
      {lectura.tipo === "mantenimiento" && <p className="fieldNote" role="status">{t.lecturaMantenimiento}</p>}

      {/* La invitación va ACÁ, apenas vio su rueda, que es el momento de
          decidir. Los datos quedan plegados debajo. */}
      <div className="previewCta">
        {lectura.tipo === "nada" && (
          <>
            <button type="button" className="btn btnPrimary" onClick={onPedirLectura}>
              {t.previewCta}
            </button>
            <p className="fieldNote">{t.previewNote}</p>
          </>
        )}

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
