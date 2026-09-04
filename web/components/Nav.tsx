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

  /**
   * En qué sección está parada la persona.
   *
   * El nav no lo decía en ningún lado: lo único con color era el acceso
   * (`.navEnter`), y al ser el único resaltado se leía como "estás acá" —
   * leyendo una nota, el nav decía "Tu cuenta" (03-09-2026).
   *
   * `startsWith` con la barra y no una igualdad: `/carta/<uuid>` no es una
   * sección del nav, pero `/legal/privacy` sí cuelga de una, y una nota
   * resuelve al listado (su `path` es el índice, porque cambiar de idioma
   * desde una nota lleva al índice del otro idioma).
   */
  const aqui = pathPara(locale);
  const enSeccion = (ruta: string) => aqui === ruta || aqui.startsWith(`${ruta}/`);
  /** Lo que distingue "estoy acá" de un enlace más, para quien no ve el color. */
  const marca = (ruta: string) =>
    enSeccion(ruta) ? ({ "aria-current": "page" as const, className: "navActual" }) : {};

  return (
    <nav className="nav">
      <div className="navInner">
        <Link className="brand" href={`/${locale}`}>
          <Logo />
          <span className="wordmark">ASTRA</span>
        </Link>

        <div className="navLinks">
          <Link href={`/${locale}/nueva`} {...marca("/nueva")}>
            {dict.newChart.navNew}
          </Link>
          {showExample && (
            <Link href={`/${locale}/ejemplo`} {...marca("/ejemplo")}>
              {dict.nav.example}
            </Link>
          )}
          <Link href={`/${locale}/precios`} {...marca("/precios")}>
            {dict.nav.precios}
          </Link>
          <Link href={`/${locale}/${NOTES_SLUG[locale]}`} {...marca(`/${NOTES_SLUG[locale]}`)}>
            {dict.nav.notes}
          </Link>
          <Link
            href={`/${locale}${signedIn ? "/cuenta" : "/entrar"}`}
            {...marca(signedIn ? "/cuenta" : "/entrar")}
            className={`navEnter${enSeccion(signedIn ? "/cuenta" : "/entrar") ? " navActual" : ""}`}
          >
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
