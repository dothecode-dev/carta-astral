"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ChartBody } from "@/components/ChartBody";
import { DatosCarta } from "@/components/DatosCarta";
import { TeaserBloques, TeaserIndice } from "@/components/Teaser";
import type { CartaDibujable } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";

// Lo que ve quien calculó su carta sin tener cuenta. Es la carta entera —la
// misma rueda y las mismas tablas que ve un usuario registrado— y lo que ya se
// puede leer de ella: el teaser y el índice del informe (spec 2026-10-17).
// Orden desde el 18-10-2026: compra chica, rueda con sus datos, bloques de a
// dos, índice y compra grande, que queda última antes del pie. Hasta el 17-10-2026 acá se ofrecía una lectura breve por
// IA gratis; se apagó porque costaba por visita y no llevaba a ninguna compra.
// El código de esa lectura sigue en el repo (`useLecturaAnonima`), sin usarse
// desde esta pantalla.

type PasoTeaser = "datos_abiertos" | "cierre_visto" | "clic_arriba" | "clic_cierre" | "mail_enviado" | "volver";

/** Un paso del teaser al contador del servidor (backend/api/conteo_api.py):
 *  sin cookies ni nada de quién fue. Nunca frena lo que cuenta: si falla, se
 *  pierde ese número y nada más. `keepalive` deja salir el pedido aunque la
 *  página se vaya al pago. */
function contarPaso(evento: PasoTeaser, moneda?: string) {
  try {
    void fetch("/api/conteo/teaser", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(moneda ? { evento, moneda } : { evento }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Sin `fetch` (un navegador muy viejo): no se cuenta.
  }
}

export function CartaPreview({
  carta,
  dict,
  locale,
  onVolver,
  precio,
  onComprar,
  comprando,
  errorCompra,
  pideMail = false,
  moneda,
}: {
  carta: CartaDibujable;
  dict: Dict;
  locale: Locale;
  onVolver: () => void;
  /** El precio del informe, ya formateado por `lib/catalogo`. `null` si el
   *  catálogo no respondió: el botón sigue, sin precio en el texto (comprar
   *  no depende de él; Stripe lo muestra antes de cobrar). */
  precio: string | null;
  /** Con `pideMail`, recibe el mail que escribió la persona. */
  onComprar: (mail?: string) => void | Promise<void>;
  comprando: boolean;
  errorCompra: string | null;
  /** En pesos: el primer clic abre el campo del mail en vez del pago, y el
   *  pago sale del botón de ese campo (Mercado Pago no devuelve el mail). */
  pideMail?: boolean;
  /** En qué moneda se mostró el precio: el conteo de los clics la separa. */
  moneda?: string;
}) {
  const t = dict.newChart;
  // Cuál se apretó: el error va junto a ese, no a una pantalla de distancia.
  const [origen, setOrigen] = useState<"arriba" | "cierre">("cierre");
  const [mailAbierto, setMailAbierto] = useState(false);
  const [mail, setMail] = useState("");
  // Cada paso, una vez por carta: volver a apretar, a pasar o a abrir no es
  // otra persona, y así los pasos del embudo se pueden dividir entre sí.
  const contado = useRef<Set<PasoTeaser>>(new Set());
  const contarUnaVez = useCallback((paso: PasoTeaser, enMoneda?: string) => {
    if (contado.current.has(paso)) return;
    contado.current.add(paso);
    contarPaso(paso, enMoneda);
  }, []);
  const cierre = useRef<HTMLElement>(null);
  useEffect(() => {
    const nodo = cierre.current;
    // Sin soporte no se cuenta: contar igual inventaría lecturas.
    if (!nodo || typeof IntersectionObserver === "undefined") return;
    const observador = new IntersectionObserver((entradas) => {
      if (!entradas.some((e) => e.isIntersecting)) return;
      contarUnaVez("cierre_visto");
      observador.disconnect();
    });
    observador.observe(nodo);
    return () => observador.disconnect();
  }, [contarUnaVez]);
  const error = (donde: "arriba" | "cierre") =>
    errorCompra && origen === donde ? (
      <p className="compraError" role="alert">
        {errorCompra}
      </p>
    ) : null;

  // Los dos botones hacen lo mismo y comparten estado: el de arriba para quien
  // ya decidió, el grande del cierre para quien leyó todo (18-10-2026).
  const boton = (grande: boolean) => {
    const donde = grande ? "cierre" : "arriba";
    // En pesos, el campo del mail ocupa el lugar del botón que se apretó.
    if (pideMail && mailAbierto && origen === donde) {
      return (
        <form
          className="form previewMail"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            // Sólo un mail con forma de mail: los intentos fallidos inflarían
            // justo el paso que se quiere medir.
            if (e.currentTarget.checkValidity()) contarUnaVez("mail_enviado", moneda);
            void onComprar(mail);
          }}
        >
          <div className="field">
            <label className="fieldLabel" htmlFor={`preview-mail-${donde}`}>
              {t.mailLabel}
            </label>
            <input
              id={`preview-mail-${donde}`}
              className="input"
              type="email"
              autoComplete="email"
              required
              autoFocus
              value={mail}
              onChange={(e) => setMail(e.target.value)}
            />
            <p className="fieldNote">{t.mailNota}</p>
          </div>
          <button type="submit" className={grande ? "btn btnPrimary btnGrande" : "btn btnPrimary"} disabled={comprando}>
            {comprando ? dict.precios.abriendo : t.mailPagar}
          </button>
        </form>
      );
    }
    return (
      <button
        type="button"
        className={grande ? "btn btnPrimary btnGrande" : "btn btnPrimary"}
        disabled={comprando}
        onClick={() => {
          contarUnaVez(grande ? "clic_cierre" : "clic_arriba", moneda);
          setOrigen(donde);
          if (pideMail) setMailAbierto(true);
          else void onComprar();
        }}
      >
        {comprando
          ? dict.precios.abriendo
          : precio
            ? t.comprarCta.replace("{precio}", precio)
            : t.comprarCtaSinPrecio}
      </button>
    );
  };

  return (
    <section className="previewCarta">
      <header className="previewHead">
        {/* El título de la página: con la carta a la vista, el encabezado del
            formulario se esconde (CSS: .formFrame:has(.previewCarta)). */}
        <h1 className="display previewTitle">{t.previewTitle}</h1>
        <p className="previewLede">{t.previewLede}</p>
        <div className="previewCtaArriba">
          {error("arriba")}
          {boton(false)}
        </div>
      </header>

      {/* La rueda primero: es lo que vino a buscar. */}
      <ChartBody chart={carta} dict={dict} locale={locale} soloRueda />

      {/* Los datos son de la rueda: van con ella, plegados. */}
      <DatosCarta chart={carta} dict={dict} locale={locale} onAbrir={() => contarUnaVez("datos_abiertos")} />

      {/* Sin teaser (un backend viejo) se muestra todo lo demás. */}
      {carta.teaser && <TeaserBloques teaser={carta.teaser} locale={locale} dict={dict} />}

      {/* El cierre: lo que trae el informe, con los temas de esta carta
          bloqueados, y pegado el botón grande. Pagar es entrar: se compra sin
          pasar por /entrar. Sin precio (el catálogo no respondió) el botón
          sigue: sacarlo dejaba la pantalla sin salida. */}
      <section className="previewCierre" ref={cierre}>
        {carta.teaser && (
          <>
            <h2 className="display previewCierreTitulo">{t.indiceTitulo}</h2>
            <TeaserIndice teaser={carta.teaser} locale={locale} dict={dict} />
          </>
        )}
        <div className="previewCta">
          {error("cierre")}
          {boton(true)}
          {carta.teaser && (
            <p className="fieldNote">
              {t.informeTrae
                .replace("{n}", String(carta.teaser.informe.secciones))
                // "always": en es, ICU no agrupa los números de cuatro cifras
                // (6000; el backend redondea a miles) y al lado de pt (6.000)
                // se vería inconsistente.
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
      </section>

      <footer className="previewPie">
        <p className="fieldNote">{t.previewPrivacidad}</p>
        <button
          type="button"
          className="btn btnGhost"
          onClick={() => {
            contarUnaVez("volver");
            onVolver();
          }}
        >
          {t.navNew}
        </button>
      </footer>
    </section>
  );
}
