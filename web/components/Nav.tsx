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
   *  la página en la que estás.
   *
   *  Puede ser una función cuando la ruta misma cambia con el idioma: la
   *  sección de notas es `/notas` en español y `/notes` en inglés, así que un
   *  path fijo mandaría a `/en/notas`, que no existe. */
  path?: string | ((code: Locale) => string);
}) {
  const pathPara = (code: Locale) => (typeof path === "function" ? path(code) : path);
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
          <Link href={`/${locale}/precios`}>{dict.nav.precios}</Link>
          <Link href={`/${locale}/${NOTES_SLUG[locale]}`}>{dict.nav.notes}</Link>
          <Link className="navEnter" href={`/${locale}${signedIn ? "/cuenta" : "/entrar"}`}>
            {signedIn ? dict.auth.account : dict.auth.navEnter}
          </Link>
        </div>

        <nav className="langs" aria-label="Idioma">
          {LOCALES.map((code) => (
            // `<a>` y no `<Link>`: cambiar de idioma cambia el segmento
            // `[locale]`, que es el del layout raíz, y en una navegación de
            // cliente React remonta el <html> con el markup del servidor, que
            // no trae `data-theme`. El tema elegido se perdía y quien estaba en
            // día aterrizaba en noche. Con una navegación de documento vuelve a
            // correr el script anti-parpadeo, antes del primer paint.
            //
            // El costo es una recarga completa al cambiar de idioma, que no es
            // una navegación frecuente ni encadenada.
            <a
              key={code}
              href={`/${code}${pathPara(code)}`}
              aria-current={code === locale ? "true" : undefined}
              hrefLang={code}
            >
              {code.toUpperCase()}
            </a>
          ))}
        </nav>

        <ThemeSwitch night={dict.theme.night} day={dict.theme.day} label={dict.theme.label} />
      </div>
    </nav>
  );
}
