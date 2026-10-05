"use client";

import { useSyncExternalStore } from "react";

import { formatearInstante } from "@/lib/instante";
import type { Locale } from "@/lib/i18n";

// Si ya estamos en el navegador con la página hidratada. Mismo patrón que
// `ThemeSwitch`: `useSyncExternalStore` en vez de copiar a un estado desde un
// efecto. En la hidratación React usa el snapshot del servidor —el HTML coincide
// y no hay mismatch— y enseguida re-renderiza con el del cliente.
const nadaQueEscuchar = () => () => {};
const enCliente = () => true;
const enServidor = () => false;

function useHidratado(): boolean {
  return useSyncExternalStore(nadaQueEscuchar, enCliente, enServidor);
}

/** Un instante que el servidor escribe en UTC y el navegador pasa a la hora de
 *  quien mira.
 *
 *  `utc` lo formatea el servidor (`instanteUtc`) y se usa tal cual hasta
 *  hidratar: recalcularlo acá daría otro string —ver `lib/instante.ts`— y la
 *  hidratación fallaría. Lo que lee Google es esa versión, con el instante
 *  exacto en `dateTime`. */
export function HoraLocal({ iso, utc, locale }: { iso: string; utc: string; locale: Locale }) {
  const texto = useHidratado() ? formatearInstante(iso, locale) : utc;
  return <time dateTime={iso}>{texto}</time>;
}

/** La aclaración de en qué zona están las horas: dice UTC hasta que el
 *  navegador las convierte. */
export function ZonaDeLasHoras({ utc, local }: { utc: string; local: string }) {
  return <p className="cieloNota">{useHidratado() ? local : utc}</p>;
}
