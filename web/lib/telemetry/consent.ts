/** El consentimiento de analítica: dónde vive, cómo se lee y quién se entera.
 *
 * Vive en `localStorage`, no en una cookie, y la razón es de arquitectura:
 * leer una cookie en el layout obliga a `cookies()`, y eso convierte en
 * dinámicas las rutas que hoy son estáticas — la vidriera entera se
 * prerenderiza en el build para los tres idiomas y no vale la pena perderlo
 * por un banner. El tema (`astra-theme`) está resuelto igual y por lo mismo.
 *
 * Consecuencia asumida: el servidor no sabe si hubo consentimiento, así que el
 * banner se decide en el cliente y aparece un instante después del primer
 * paint. Es abajo y no tapa contenido.
 *
 * Es un almacén externo con suscripción para que el banner pueda leerlo con
 * `useSyncExternalStore` en vez de copiarlo a un estado dentro de un efecto:
 * la fuente de verdad es el almacenamiento, no React.
 */

const CLAVE = "astra-consent";

export type Consentimiento = "si" | "no";

const oyentes = new Set<() => void>();

function avisar(): void {
  for (const oyente of oyentes) oyente();
}

/** `null` = todavía no decidió, que es distinto de haber dicho que no. */
export function leerConsentimiento(): Consentimiento | null {
  // Falla en SSR, en modo incógnito de algunos navegadores y con el
  // almacenamiento bloqueado por política. En todos esos casos "no decidió" es
  // la respuesta correcta y segura: sin decisión no se mide.
  try {
    const v = window.localStorage.getItem(CLAVE);
    return v === "si" || v === "no" ? v : null;
  } catch {
    return null;
  }
}

/** En el servidor no hay decisión que leer, y el banner no se pinta hasta que
 *  el navegador la lea. Devolver siempre lo mismo evita el bucle de renders. */
export function leerEnServidor(): Consentimiento | null {
  return "no";
}

export function suscribir(oyente: () => void): () => void {
  oyentes.add(oyente);
  return () => void oyentes.delete(oyente);
}

export function guardarConsentimiento(valor: Consentimiento): void {
  try {
    window.localStorage.setItem(CLAVE, valor);
  } catch {
    // Si no se puede guardar, la decisión vale para esta visita y el banner
    // vuelve en la próxima. Molesto, pero no se pierde ni se inventa consentimiento.
  }
  avisar();
}

/** Para el enlace del pie: volver a preguntar.
 *
 * Retirar el consentimiento tiene que ser tan fácil como darlo — es requisito
 * del RGPD, no una cortesía. */
export function olvidarConsentimiento(): void {
  try {
    window.localStorage.removeItem(CLAVE);
  } catch {
    // Ver arriba: sin almacenamiento no hay nada que borrar.
  }
  avisar();
}
