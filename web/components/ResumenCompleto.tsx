import type { Dict } from "@/lib/i18n";

/** Una fila de `GET /api/charts/<uuid>/informe/indice/`: título de una
 *  sección del informe completo y, si ya está escrita, el arranque de su
 *  primer párrafo. La misma forma sirve para una sección sin generar
 *  (`parrafo` vacío, `restante` = objetivo de palabras) y una ya generada
 *  (`parrafo` recortado, `restante` = lo que falta de esa sección) — no hay
 *  que ramificar por eso. */
export type SeccionIndice = {
  slug: string;
  titulo: string;
  parrafo: string;
  restante: number;
};

/**
 * El pie de la lectura breve: el índice del informe completo, con el
 * arranque de cada sección cuando ya existe. Es la vidriera de lo que se
 * vende (RF3) — de presentación, sin estado ni llamadas propias.
 *
 * Decidir SI se muestra no es trabajo de este componente. Vive en la página:
 * quien ya tiene el informe completo (`interpretations[lang]` incluye
 * `"largo"`) no necesita que se le venda lo que ya compró, y la página
 * refleja eso pasando `secciones` vacío en vez de llamar al backend. Acá
 * sólo se cubre el caso límite de que igual llegue vacío.
 */
export function ResumenCompleto({
  secciones,
  dict,
}: {
  secciones: SeccionIndice[];
  dict: Dict;
}) {
  if (secciones.length === 0) return null;

  return (
    <section className="resumenCompleto">
      <p className="eyebrow">{dict.chart.resumenTitulo}</p>
      <div className="resumenSecciones">
        {secciones.map((seccion) => (
          <div key={seccion.slug} className="resumenSeccion">
            <h3 className="resumenSeccionTitulo">{seccion.titulo}</h3>
            {seccion.parrafo && <p className="resumenSeccionParrafo">{seccion.parrafo}</p>}
            <p className="fieldNote">
              {dict.chart.resumenRestante.replace("{n}", String(seccion.restante))}
            </p>
          </div>
        ))}
      </div>
      <p className="resumenCta">{dict.chart.resumenCta}</p>
    </section>
  );
}
