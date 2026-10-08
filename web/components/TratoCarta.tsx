"use client";

import { useId, useState } from "react";

import { type Trato, TRATOS } from "@/lib/datosCarta";
import type { Dict } from "@/lib/i18n";

const TRATO_CLAVE = {
  femenino: "tratoFemenino",
  masculino: "tratoMasculino",
  neutro: "tratoNeutro",
} as const;

/** Cómo quiere la persona que le hablemos, cambiable con la carta ya creada.
 *  Las etiquetas son las del formulario de alta (`newChart`): una sola fuente.
 *  Vale para lo que se escriba o traduzca desde ahora; lo ya escrito no cambia. */
export function TratoCarta({
  chartId,
  trato: inicial,
  dict,
}: {
  chartId: string;
  trato: Trato;
  dict: Dict;
}) {
  const id = useId();
  const [trato, setTrato] = useState<Trato>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(false);
  const t = dict.newChart;

  async function cambiar(nuevo: Trato) {
    const anterior = trato;
    setTrato(nuevo);
    setError(false);
    setGuardando(true);
    try {
      const res = await fetch(`/api/charts/${chartId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trato: nuevo }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
    } catch {
      setTrato(anterior);
      setError(true);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="field tratoCarta">
      <label className="fieldLabel" htmlFor={id}>
        {dict.chart.tratoTitulo}
      </label>
      <select
        id={id}
        className="input"
        value={trato}
        disabled={guardando}
        onChange={(e) => void cambiar(e.target.value as Trato)}
      >
        <option value="">{t.tratoVacio}</option>
        {TRATOS.map((v) => (
          <option key={v} value={v}>
            {t[TRATO_CLAVE[v]]}
          </option>
        ))}
      </select>
      <p className="fieldNote">{dict.chart.tratoAclaracion}</p>
      {error && (
        <p className="fieldNote" role="alert">
          {dict.chart.tratoError}
        </p>
      )}
    </div>
  );
}
