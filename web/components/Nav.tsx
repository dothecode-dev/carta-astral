import Link from "next/link";

import { Logo } from "@/components/Logo";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { LOCALES, NOTES_SLUG, type Dict, type Locale } from "@/lib/i18n";

export function Nav({
  locale,
  dict,
  path = "",
  signedIn = false,
  showExample = true,
}: {
  locale: Locale;
  dict: Dict;
  /** Con sesión, el acceso apunta a la cuenta en vez de al login. */
  signedIn?: boolean;
  /** La carta de ejemplo existe para convencer a quien no tiene la suya: se
   *  esconde cuando ya hay cartas propias. Las páginas públicas no saben si hay
   *  sesión —son estáticas—, así que ahí se muestra siempre. */
  showExample?: boolean;
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
          <Link href={`/${locale}/nueva`}>{dict.newChart.navNew}</Link>
          {showExample && <Link href={`/${locale}/ejemplo`}>{dict.nav.example}</Link>}
          <Link href={`/${locale}/${NOTES_SLUG[locale]}`}>{dict.nav.notes}</Link>
          <Link href={`/${locale}#descargar`}>{dict.nav.download}</Link>
          <Link className="navEnter" href={`/${locale}${signedIn ? "/cuenta" : "/entrar"}`}>
            {signedIn ? dict.auth.account : dict.auth.navEnter}
          </Link>
        </div>

        <nav className="langs" aria-label="Idioma">
          {LOCALES.map((code) => (
            <Link
              key={code}
              href={`/${code}${path}`}
              aria-current={code === locale ? "true" : undefined}
              hrefLang={code}
              // Es la misma página en otro idioma: mandarte al principio sería
              // hacerte buscar de nuevo dónde estabas leyendo.
              scroll={false}
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
