/**
 * De dónde llegó la visita, para que el servidor cuente canal y lugar sin
 * cookies (backend/api/conteo.py).
 *
 * Se captura UNA vez, al entrar al sitio (`CapturaProcedencia` en el layout), y
 * vive en memoria: una navegación interna de Next no la pisa, y nada se guarda
 * en el navegador. De la página anterior sólo se toma el origen (sin la ruta ni
 * la búsqueda), y el servidor igual lo reduce a una lista cerrada de canales.
 */

export type Procedencia = { utm_source: string; referrer: string; zona: string };

let capturada: Omit<Procedencia, "zona"> | null = null;

export function capturarProcedencia(lugar: Location = window.location, anterior: string = document.referrer): void {
  if (capturada) return;
  const utm = new URLSearchParams(lugar.search).get("utm_source") ?? "";
  let referrer = "";
  try {
    const previa = new URL(anterior);
    if (previa.hostname && previa.hostname !== lugar.hostname) referrer = previa.origin;
  } catch {
    // Sin página anterior (o una que no es URL): entró directo.
  }
  capturada = { utm_source: utm.slice(0, 40), referrer };
}

export function leerProcedencia(): Procedencia {
  if (!capturada) capturarProcedencia();
  let zona = "";
  try {
    zona = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  } catch {
    // Un navegador sin Intl: el servidor lo cuenta como «desconocida».
  }
  return { ...(capturada ?? { utm_source: "", referrer: "" }), zona };
}

/** Sólo para los tests. */
export function _reiniciarProcedencia(): void {
  capturada = null;
}
