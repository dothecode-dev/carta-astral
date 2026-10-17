/**
 * De dónde llegó la visita, para que el servidor cuente canal y lugar sin
 * cookies (backend/api/conteo.py).
 *
 * Se captura UNA vez, al entrar al sitio (`CapturaProcedencia` en el layout), y
 * vive en memoria: una navegación interna de Next no la pisa, y nada se guarda
 * en el navegador. De la página anterior sólo se toma el origen (sin la ruta ni
 * la búsqueda), y el servidor igual lo reduce a una lista cerrada de canales.
 */

export type Procedencia = { utm_source: string; gclid: boolean; referrer: string; zona: string };

let capturada: Omit<Procedencia, "zona"> | null = null;

export function capturarProcedencia(lugar: Location = window.location, anterior: string = document.referrer): void {
  if (capturada) return;
  const params = new URLSearchParams(lugar.search);
  const utm = params.get("utm_source") ?? "";
  // Google Ads marca sus clics con gclid (o gbraid/wbraid en iOS) aunque no
  // haya utm_source. Sólo se manda SI estaba, nunca el valor.
  const gclid = ["gclid", "gbraid", "wbraid"].some((p) => params.has(p));
  let referrer = "";
  try {
    const previa = new URL(anterior);
    if (previa.hostname && previa.hostname !== lugar.hostname) {
      // `origin` es "null" para esquemas que no son http (android-app://… de la
      // app de Google o de Gmail): ahí va el esquema con el paquete.
      referrer = previa.origin !== "null" ? previa.origin : `${previa.protocol}//${previa.hostname}`;
    }
  } catch {
    // Sin página anterior (o una que no es URL): entró directo.
  }
  capturada = { utm_source: utm.slice(0, 40), gclid, referrer };
}

export function leerProcedencia(): Procedencia {
  if (!capturada) capturarProcedencia();
  let zona = "";
  try {
    zona = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  } catch {
    // Un navegador sin Intl: el servidor lo cuenta como «desconocida».
  }
  return { ...(capturada ?? { utm_source: "", gclid: false, referrer: "" }), zona };
}

/** Sólo para los tests. */
export function _reiniciarProcedencia(): void {
  capturada = null;
}
