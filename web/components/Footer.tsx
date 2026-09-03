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
        </nav>
      </div>
    </footer>
  );
}
