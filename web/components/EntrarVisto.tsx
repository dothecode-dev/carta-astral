"use client";

import { useEffect } from "react";

import { track } from "@/lib/telemetry";

/** Deja rastro de que alguien llegó a /entrar, sin importar si el login
 *  después sale bien. Sin esto, un botón de Google que nunca aparece o
 *  alguien que se da vuelta antes de intentarlo no dejaban ningún rastro: así
 *  se perdió, el 08-09-2026, lo que vieron tres de seis visitas a esta
 *  pantalla.
 *
 *  Un componente aparte y no un `track()` suelto en `page.tsx` porque esa
 *  página es un server component —no puede llamar a `track`, que vive del
 *  lado del cliente—. Responsabilidad única: medir la visita, nada más.
 *
 *  `next` es la ruta de destino ya validada por `destinoSeguro`, nunca datos
 *  personales: es lo único que viaja en el evento. */
export function EntrarVisto({ next }: { next?: string | null }) {
  useEffect(() => {
    track("entrar_visto", next ? { next } : {});
    // Sólo importa la primera visita a esta pantalla: `next` no cambia
    // durante la vida de este componente porque lo decide el server component
    // que lo monta, así que no hace falta volver a disparar si cambiara.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
