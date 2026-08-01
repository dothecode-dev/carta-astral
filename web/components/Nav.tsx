import Link from "next/link";

import { Logo } from "@/components/Logo";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { LOCALES, type Dict, type Locale } from "@/lib/i18n";

export function Nav({
  locale,
  dict,
  path = "",
}: {
  locale: Locale;
  dict: Dict;
  /** Lo que va después del idioma, para que cambiar de idioma no te saque de
   *  la página en la que estás. */
  path?: string;
}) {
  return (
    <nav className="nav">
      <div className="navInner">
        <Link className="brand" href={`/${locale}`}>
          <Logo />
          <span className="wordmark">ASTRA</span>
        </Link>

        <div className="navLinks">
          <Link href={`/${locale}/ejemplo`}>{dict.nav.example}</Link>
          <Link href={`/${locale}`}>{dict.nav.notes}</Link>
          <Link href={`/${locale}#descargar`}>{dict.nav.download}</Link>
        </div>

        <nav className="langs" aria-label="Idioma">
          {LOCALES.map((code) => (
            <Link
              key={code}
              href={`/${code}${path}`}
              aria-current={code === locale ? "true" : undefined}
              hrefLang={code}
            >
              {code.toUpperCase()}
            </Link>
          ))}
        </nav>

        <ThemeSwitch night={dict.theme.night} day={dict.theme.day} label={dict.theme.label} />
      </div>
    </nav>
  );
}
