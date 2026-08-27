/** Arranque de la telemetría del navegador.
 *
 * Next 16 corre este archivo antes de que la app sea interactiva; es el lugar
 * que la doc señala para analítica (`node_modules/next/dist/docs/01-app/
 * 03-api-reference/03-file-conventions/instrumentation-client.md`).
 *
 * Acá no se decide nada: si no hubo consentimiento en una visita anterior,
 * `activarSiConsintio` no hace nada y `posthog-js` ni se descarga.
 */

import { activarSiConsintio, capturarPagina } from "@/lib/telemetry";

// Se lee ahora y no dentro del `then`: cargar el SDK tarda, y si el visitante
// hace clic en un enlace mientras tanto, `window.location.href` ya apunta a la
// segunda página. La de entrada —la que dice de dónde viene la gente— es ésta.
const entrada = window.location.href;

void activarSiConsintio().then(() => {
  // La primera vista no llega por una transición de router: hay que mandarla
  // a mano o se pierde.
  capturarPagina(entrada);
});

/** Cada navegación del router.
 *
 * Se dispara al *empezar* la transición, así que una navegación abortada
 * cuenta igual. Es la señal que da Next y el error es despreciable frente a
 * perder las vistas de toda la navegación cliente. */
export function onRouterTransitionStart(url: string): void {
  capturarPagina(url);
}
