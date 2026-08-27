"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { activar, capturarPagina, desactivar, medicionDisponible, track } from "@/lib/telemetry";
import {
  guardarConsentimiento,
  leerConsentimiento,
  leerEnServidor,
  suscribir,
} from "@/lib/telemetry/consent";
import type { Locale } from "@/lib/i18n";

/** Recibe las cadenas sueltas, no el diccionario entero.
 *
 * `DangerZone` recibe el `Dict` completo siendo componente de cliente, y eso
 * manda los tres idiomas al navegador en cada carga. Acá no. */
export function ConsentBanner({
  locale,
  text,
  accept,
  reject,
  more,
}: {
  locale: Locale;
  text: string;
  accept: string;
  reject: string;
  more: string;
}) {
  // La fuente de verdad es `localStorage`, no un estado de React: copiarlo a un
  // `useState` dentro de un efecto es exactamente lo que el linter rechaza, y
  // además dejaría al banner y al enlace del pie con dos verdades distintas.
  const decision = useSyncExternalStore(suscribir, leerConsentimiento, leerEnServidor);

  // Sin token de PostHog no hay nada que medir, y preguntar por algo que no
  // ocurre sólo gasta la atención del visitante. El hook va antes del return
  // porque no se puede llamar condicionalmente.
  if (!medicionDisponible) return null;

  // `null` es "todavía no decidió". Un "no" guardado no vuelve a preguntar:
  // insistir con el banner en cada visita es la forma más común de convertir
  // un rechazo en un consentimiento que no vale nada.
  if (decision !== null) return null;

  async function aceptar() {
    guardarConsentimiento("si");
    await activar();
    track("consentimiento", { decision: "si" });
    // La visita ya ocurrió y no la medimos: sin esto, la página de entrada de
    // todo el que acepta se pierde, que es justo la que dice de dónde viene.
    capturarPagina(window.location.href);
  }

  function rechazar() {
    guardarConsentimiento("no");
    // Por definición no se registra: medir el rechazo sería medir a quien
    // acaba de decir que no. El total de PostHog es, entonces, el de los que
    // aceptaron — no el tráfico real.
    desactivar();
  }

  return (
    // `region` y no `dialog`: no es modal, no atrapa el foco y no tapa la
    // página. Un `dialog` sin nombre accesible se anuncia como un diálogo
    // anónimo, que es peor que no declararlo.
    <aside className="consentBar" role="region" aria-label={text}>
      <p className="consentText">
        {text} <Link href={`/${locale}/legal/privacy`}>{more}</Link>
      </p>
      <div className="consentActions">
        <button type="button" className="btn btnGhost" onClick={rechazar}>
          {reject}
        </button>
        <button type="button" className="btn btnPrimary" onClick={() => void aceptar()}>
          {accept}
        </button>
      </div>
    </aside>
  );
}
