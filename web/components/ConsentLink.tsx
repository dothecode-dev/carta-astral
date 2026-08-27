"use client";

import { olvidarConsentimiento } from "@/lib/telemetry/consent";
import { desactivar } from "@/lib/telemetry";

/** Vuelve a abrir el banner desde el pie.
 *
 * El RGPD pide que retirar el consentimiento sea tan fácil como darlo; sin
 * este enlace la decisión queda enterrada en `localStorage` para siempre.
 * Es un botón y no un enlace porque no navega a ninguna parte: borrar la
 * decisión avisa al banner, que vuelve a aparecer solo. */
export function ConsentLink({ label }: { label: string }) {
  return (
    <button
      type="button"
      className="footLinkButton"
      onClick={() => {
        // Primero se corta la medición, después se olvida la decisión: al
        // revés queda un instante midiendo a quien está por decir que no.
        desactivar();
        olvidarConsentimiento();
      }}
    >
      {label}
    </button>
  );
}
