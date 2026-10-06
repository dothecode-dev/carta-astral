"use client";

import { useEffect, useRef, useState } from "react";

import { NatalWheel } from "@/components/NatalWheel";
import { VINCULO } from "@/content/vinculo";
import { toWheel } from "@/lib/chart";
import { ASPECT_NAMES, PLANET_NAME_BY_KEY, type Dict, type Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";
import type { TipoVinculo, VinculoPreview as Datos } from "@/lib/vinculo";

// Lo que ve quien cargó las dos personas: sus dos ruedas y los contactos más
// cerrados entre los planetas personales, cada uno con una frase fija. Es la
// fase 1 de Vínculo: se publica para medir cuánta gente llega hasta acá y
// cuánta aprieta «leer el vínculo completo», antes de construir la compra.
//
// El botón todavía no compra nada: registra la intención y avisa que el informe
// sale pronto. No pide mail a propósito (la política de privacidad promete no
// perfilar, y juntar mails la obligaría a cambiar antes de medir nada).
//
// Los alias son texto del usuario y se muestran como texto: React los escapa, y
// nunca llegaron al backend.

export function VinculoPreview({
  locale,
  dict,
  preview,
  tipo,
  alias,
}: {
  locale: Locale;
  dict: Dict;
  preview: Datos;
  tipo: TipoVinculo;
  alias: { a: string; b: string };
}) {
  const t = VINCULO[locale];
  const planetas = PLANET_NAME_BY_KEY[locale];
  const aspectos = ASPECT_NAMES[locale];
  const [avisado, setAvisado] = useState(false);

  // Una vista por render real. En desarrollo React monta dos veces, y sin esta
  // guarda cada vista contaría doble.
  const visto = useRef(false);
  useEffect(() => {
    if (visto.current) return;
    visto.current = true;
    track("vinculo_preview_visto", { tipo });
  }, [tipo]);

  const nombreA = alias.a || t.personaA;
  const nombreB = alias.b || t.personaB;

  function pedirInforme() {
    // Dos clics son una sola intención: el numerador no puede inflarse.
    if (avisado) return;
    setAvisado(true);
    track("vinculo_cta_click", { tipo });
  }

  return (
    <section className="previewCarta">
      <header className="previewHead">
        <h2 className="display previewTitle">{t.previewTitle}</h2>
        <p className="previewLede">{t.previewLede}</p>
      </header>

      <div className="vinculoColumnas">
        {[
          { nombre: nombreA, carta: preview.a },
          { nombre: nombreB, carta: preview.b },
        ].map(({ nombre, carta }, i) => {
          const rueda = toWheel(carta);
          return (
            <div className="vinculoColumna" key={i}>
              <h3 className="fieldLabel">{nombre}</h3>
              {rueda ? (
                <NatalWheel chart={rueda} alt={`${t.ruedaAlt} ${nombre}`} />
              ) : (
                // Sin hora no hay Ascendente ni casas, así que no hay rueda
                // que dibujar: se dice por qué en vez de dejar un hueco.
                <div className="emptyCharts">
                  <p className="emptyChartsText">
                    <strong>{dict.chart.noWheel}</strong>
                  </p>
                  <p className="emptyChartsText">{t.sinHora}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <section className="vinculoAspectos">
        <h3 className="fieldLabel">{t.aspectosTitulo}</h3>
        {preview.aspectos.length > 0 ? (
          <ul className="vinculoLista">
            {preview.aspectos.map((a) => (
              <li key={`${a.p_a}|${a.p_b}|${a.aspecto}`}>
                <strong>
                  {planetas[a.p_a] ?? a.p_a} ({nombreA}) · {aspectos[a.aspecto] ?? a.aspecto} ·{" "}
                  {planetas[a.p_b] ?? a.p_b} ({nombreB})
                </strong>
                <p>{a.frase}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p>{t.sinAspectos}</p>
        )}
      </section>

      <div className="previewCta">
        <button type="button" className="btn btnPrimary" onClick={pedirInforme}>
          {t.cta}
        </button>
        {avisado && (
          <p className="fieldNote" role="status">
            {t.ctaPronto}
          </p>
        )}
      </div>

      <footer className="previewPie">
        <p className="fieldNote">{t.privacidad}</p>
      </footer>
    </section>
  );
}
