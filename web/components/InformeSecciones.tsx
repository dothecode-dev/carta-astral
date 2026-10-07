"use client";

import { useEffect, useRef } from "react";

import { Reading } from "@/components/Reading";
import { track } from "@/lib/telemetry";

export type SeccionEscrita = { slug: string; titulo: string; texto: string };

/**
 * Las secciones del informe largo, cada una con su título del catálogo como
 * `h2` con ancla, y opcionalmente el índice arriba. Lo usan la lectura
 * terminada (con índice) y la espera, que muestra lo ya escrito (sin índice).
 *
 * Mide hasta dónde se lee: `seccion_informe_leida` sale cuando el FINAL de una
 * sección entra en pantalla, con los segundos desde que entró su título. Pasar
 * por un título haciendo scroll no es leer.
 */
export function InformeSecciones({
  secciones,
  indice,
  etiquetaIndice,
}: {
  secciones: SeccionEscrita[];
  indice: boolean;
  etiquetaIndice?: string;
}) {
  const raiz = useRef<HTMLDivElement>(null);
  const inicio = useRef(new Map<string, number>());
  const contadas = useRef(new Set<string>());

  useEffect(() => {
    const nodo = raiz.current;
    // Sin IntersectionObserver no se emite: un fallback que dispare igual
    // daría el falso positivo que este evento existe para evitar.
    if (!nodo || typeof IntersectionObserver === "undefined") return;
    const orden = new Map(secciones.map((s, i) => [s.slug, i + 1]));
    const observador = new IntersectionObserver((entradas) => {
      const visibles = entradas.filter((e) => e.isIntersecting).map((e) => e.target as HTMLElement);
      // Primero los títulos: si título y final llegan en el mismo aviso, el
      // final tiene que encontrar el inicio ya anotado.
      for (const el of visibles) {
        const slug = el.dataset.inicio;
        if (slug && !inicio.current.has(slug)) inicio.current.set(slug, Date.now());
      }
      for (const el of visibles) {
        const slug = el.dataset.fin;
        if (!slug || contadas.current.has(slug)) continue;
        contadas.current.add(slug);
        const desde = inicio.current.get(slug) ?? Date.now();
        track("seccion_informe_leida", {
          slug,
          orden: orden.get(slug) ?? 0,
          segundos: Math.round((Date.now() - desde) / 1000),
        });
      }
    });
    nodo.querySelectorAll("[data-inicio], [data-fin]").forEach((el) => observador.observe(el));
    return () => observador.disconnect();
  }, [secciones]);

  return (
    <div ref={raiz} className="informeSecciones">
      {indice && (
        <nav className="informeIndice" aria-label={etiquetaIndice}>
          {etiquetaIndice && <p className="eyebrow">{etiquetaIndice}</p>}
          <ol>
            {secciones.map((s) => (
              <li key={s.slug}>
                <a href={`#${s.slug}`}>{s.titulo}</a>
              </li>
            ))}
          </ol>
        </nav>
      )}
      {secciones.map((s) => (
        <section key={s.slug} className="informeSeccion">
          <h2 id={s.slug} data-inicio={s.slug} className="readingTitle">
            {s.titulo}
          </h2>
          <Reading texto={s.texto} />
          <span data-fin={s.slug} aria-hidden="true" />
        </section>
      ))}
    </div>
  );
}
