import Link from "next/link";

import { ConsentLink } from "@/components/ConsentLink";
import { LEGAL_CONTACT } from "@/content/legal";
import type { Dict, Locale } from "@/lib/i18n";

// El mismo pie en todas las páginas. Estaba copiado en tres y ausente en cinco,
// así que los legales no se alcanzaban desde media web.
//
// Trae su propio marco (`footInner`), igual que `Nav` con `navInner`: la banda
// va de borde a borde y el contenido queda contenido, sin depender de quién lo
// envuelva. Antes era un <footer> pelado y su ancho lo decidía cada página —en
// diez estaba dentro de `.docFrame` y andaba de casualidad, y en /precios quedó
// afuera y se estiró hasta el borde de la ventana (03-09-2026)—.
export function Footer({ locale, dict }: { locale: Locale; dict: Dict }) {
  return (
    <footer className="foot">
      <div className="footInner">
        <span>{dict.foot.brand}</span>
        <nav className="footLinks">
          <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
          <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
          <a href={`mailto:${LEGAL_CONTACT}`}>{dict.foot.contact}</a>
          <ConsentLink label={dict.consent.footLink} />
          {/* Res. SCI 424/2020: acceso fácil y directo desde la página de
              inicio, sin registro. Está en el pie de TODAS las páginas. */}
          <Link href={`/${locale}/arrepentimiento`}>{dict.foot.arrepentimiento}</Link>
        </nav>
        {/* Data Fiscal (F. 960/D de ARCA): el QR que lleva a la situación
            fiscal del vendedor, con el logo y el enlace que da ARCA. El logo
            va por https (el HTML de ARCA lo trae en http y el navegador lo
            bloquearía); el enlace queda como lo entrega ARCA. */}
        <a
          className="footDataFiscal"
          href="http://qr.afip.gob.ar/?qr=ubYBPcTLEsiYwH81mDC7Uw,,"
          target="_F960AFIPInfo"
          rel="noopener noreferrer"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="https://www.afip.gob.ar/images/f960/DATAWEB.jpg" alt="Data Fiscal" height={56} />
        </a>
      </div>
    </footer>
  );
}
