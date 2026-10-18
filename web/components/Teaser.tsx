import { tituloCuerpoEnSigno } from "@/components/Firma";
import type { Teaser as TeaserDatos } from "@/lib/chart";
import type { Dict, Locale } from "@/lib/i18n";

/** Candado de los temas bloqueados. Decorativo: la etiqueta accesible va en el
 *  `<span role="img">` que lo envuelve, una sola por tema. */
function Candado() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.2 7V5a2.8 2.8 0 0 1 5.6 0v2" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

/**
 * Lo que se lee de la carta sin cuenta y sin pagar (spec 2026-10-17): un
 * párrafo fijo por posición —Sol, Luna, Ascendente…—. Lo escribe el backend
 * sin llamar al modelo, ya en los tres idiomas: acá sólo se elige el del
 * idioma de la página.
 */
export function TeaserBloques({ teaser, locale, dict }: { teaser: TeaserDatos; locale: Locale; dict: Dict }) {
  return (
    <div className="teaserBloques">
      {teaser.bloques.map((bloque) => (
        <section key={bloque.cuerpo} className="teaserBloque">
          <h3 className="teaserTitulo">{tituloCuerpoEnSigno(bloque.cuerpo, bloque.signo, dict, locale)}</h3>
          <p className="teaserTexto">{bloque.textos[locale]}</p>
        </section>
      ))}
    </div>
  );
}

/**
 * El índice del informe con los temas de ESTA carta a la vista pero
 * bloqueados. Va pegado al botón grande de compra: es lo que se está por
 * comprar (18-10-2026).
 */
export function TeaserIndice({ teaser, locale, dict }: { teaser: TeaserDatos; locale: Locale; dict: Dict }) {
  const t = dict.newChart;
  return (
    <ol className="teaserIndice">
      {teaser.indice.map((seccion) => (
        <li key={seccion.slug} className="teaserSeccion">
          <h3 className="teaserSeccionTitulo">{seccion.titulos[locale]}</h3>
          {seccion.temas.length > 0 && (
            <ul className="teaserTemas">
              {seccion.temas.map((tema, i) => (
                <li key={i} className="teaserTema">
                  <span role="img" aria-label={t.temaBloqueado} className="teaserCandado">
                    <Candado />
                  </span>
                  {tema[locale]}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
