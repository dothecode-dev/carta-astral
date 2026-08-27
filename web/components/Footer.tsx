import Link from "next/link";

import { ConsentLink } from "@/components/ConsentLink";
import { LEGAL_CONTACT } from "@/content/legal";
import type { Dict, Locale } from "@/lib/i18n";

// El mismo pie en todas las páginas. Estaba copiado en tres y ausente en cinco,
// así que los legales no se alcanzaban desde media web.
export function Footer({ locale, dict }: { locale: Locale; dict: Dict }) {
  return (
    <footer className="foot">
      <span>{dict.foot.brand}</span>
      <nav className="footLinks">
        <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
        <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
        <a href={`mailto:${LEGAL_CONTACT}`}>{dict.foot.contact}</a>
        <ConsentLink label={dict.consent.footLink} />
      </nav>
    </footer>
  );
}
