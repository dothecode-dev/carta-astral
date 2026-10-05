import { INTL_LOCALE, type Locale } from "@/lib/i18n";

const OPCIONES: Intl.DateTimeFormatOptions = {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
};

/** Un instante como texto, en UTC o en la zona de quien lo ejecuta.
 *
 *  Ojo: el mismo pedido NO da el mismo string en Node y en el navegador. Cada
 *  uno trae su ICU, y difieren en caracteres invisibles —el espacio antes de
 *  «p. m.» es U+202F en uno y un espacio común en otro—. Por eso la versión
 *  UTC se formatea una sola vez, en el servidor, y viaja como prop: si el
 *  navegador la recalculara, la hidratación fallaría con dos textos que se ven
 *  idénticos (medido el 05-10-2026 en Chrome contra Node). */
export function formatearInstante(iso: string, locale: Locale, timeZone?: string): string {
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], { ...OPCIONES, timeZone }).format(new Date(iso));
}

/** La versión que escribe el servidor y lee Google. */
export function instanteUtc(iso: string, locale: Locale): string {
  return `${formatearInstante(iso, locale, "UTC")} UTC`;
}
