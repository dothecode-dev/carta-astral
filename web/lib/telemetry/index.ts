/** Telemetría de la web. Todo pasa por acá: no hay otro punto de salida.
 *
 * Dos invariantes, las dos con test en `tests/telemetry.test.ts`:
 *   1. Sin `NEXT_PUBLIC_POSTHOG_KEY` nada se inicializa y todo es no-op. El
 *      build corre dos veces en CI, una con las variables vacías, porque un
 *      `ARG` ausente en el Dockerfile deja la variable en `""` y eso ya rompió
 *      un deploy.
 *   2. Sin consentimiento explícito no sale un solo evento, y `posthog-js` ni
 *      siquiera se descarga: la carga es dinámica y ocurre al aceptar.
 */

import type { EventoNombre, EventoProps } from "./events";
import { leerConsentimiento } from "./consent";

export type { EventoNombre, EventoProps } from "./events";

const CLAVE = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? "";

/** Si hay algo que medir.
 *
 * Sin token no se mide nada, y entonces tampoco corresponde pedir permiso:
 * pedir consentimiento para una medición que no existe es ruido para el
 * visitante y una pregunta cuya respuesta no cambia nada. Pasó en producción,
 * cuando el primer deploy salió sin la variable cargada. */
export const medicionDisponible = CLAVE !== "";

/** El proxy propio del sitio, servido por los rewrites de `next.config.ts`.
 *
 * Apuntar al dominio de PostHog hace que los bloqueadores de publicidad se
 * coman una parte grande de las visitas — bloquean por dominio. La ruta se
 * llama `/rueda` y no `/analytics` o `/ingest` por lo mismo: esos nombres
 * también están en las listas. */
const HOST = "/rueda";

/** La instancia viva. `null` mientras no haya consentimiento: es también la
 *  bandera que hace no-op a `track`. */
let ph: import("posthog-js").PostHog | null = null;
let cargando: Promise<void> | null = null;
/** `posthog.init` sólo puede correr una vez por página: el SDK es un singleton
 *  y una segunda llamada no vuelve a habilitar la captura. */
let iniciado = false;

/** Un uuid en la ruta identifica a una persona tan bien como un nombre.
 *
 * PostHog agrega `$current_url` y `$pathname` por su cuenta, y en `/carta/<uuid>`
 * eso viaja con el identificador de la carta adentro. Se normaliza a `[id]`
 * antes de que salga: lo que interesa es cuánta gente ve una carta, nunca cuál. */
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function normalizarRuta(valor: string): string {
  return valor.replace(UUID, "[id]");
}

/** Si el valor es una URL o una ruta, que es lo único que hay que normalizar.
 *
 * Sanear *todo* string parecía lo más seguro y era un error: `before_send`
 * también recibe `distinct_id` y `$device_id`, que son uuid, y reemplazarlos
 * por `[id]` deja a todos los visitantes compartiendo el mismo identificador
 * —o sea, una sola persona—. Se vio en producción: la columna Distinct ID de
 * PostHog decía, literal, `[id]`. */
function esRuta(valor: string): boolean {
  return valor.startsWith("/") || valor.startsWith("http://") || valor.startsWith("https://");
}

function limpiar(props: Record<string, unknown>): Record<string, unknown> {
  const limpio: Record<string, unknown> = {};
  for (const [clave, valor] of Object.entries(props)) {
    limpio[clave] = typeof valor === "string" && esRuta(valor) ? normalizarRuta(valor) : valor;
  }
  return limpio;
}

/** Arranca PostHog. Idempotente: llamarla dos veces no crea dos instancias. */
export async function activar(): Promise<void> {
  if (!CLAVE || ph || typeof window === "undefined") return;
  if (cargando) return cargando;

  cargando = (async () => {
    try {
      const { default: posthog } = await import("posthog-js");
      if (iniciado) {
        // Segunda vuelta: el SDK ya vive en la página y `init` no vuelve a
        // habilitar la captura. Sin esto, aceptar → revocar desde el pie →
        // aceptar de nuevo dejaba de medir hasta recargar la página.
        posthog.opt_in_capturing();
      } else {
        posthog.init(CLAVE, {
          api_host: HOST,
          ui_host: "https://us.posthog.com",
          // Los mandamos nosotros, con la ruta ya normalizada. El automático
          // manda la URL cruda, uuid incluido.
          capture_pageview: false,
          // Clicks y formularios automáticos: es lo que mandaría el lugar de
          // nacimiento a Estados Unidos el día que alguien toque el buscador.
          autocapture: false,
          disable_session_recording: true,
          // No usamos encuestas y cargarlas trae un script más en cada visita.
          disable_surveys: true,
          // No usamos feature flags, y el pedido de flags escapaba al saneo:
          // manda `$initial_current_url` con el uuid de la carta crudo, que es
          // justo lo que `before_send` está para evitar.
          advanced_disable_flags: true,
          // Que el SDK no recoja por su cuenta lo que parezca dato personal.
          mask_personal_data_properties: true,
          // Sin perfiles de visitantes anónimos: los eventos se cuentan igual y
          // la política promete no perfilar con fines de marketing.
          person_profiles: "identified_only",
          // `sanitize_properties` quedó deprecado en esta versión ("Use
          // before_send instead") y sólo alcanzaba las props de eventos.
          before_send: (evento) => {
            if (evento?.properties) evento.properties = limpiar(evento.properties);
            return evento;
          },
        });
        iniciado = true;
      }
      ph = posthog;
    } catch {
      // Un bloqueador, una red caída o un import que falla no pueden romper la
      // página. Sin instancia, todo lo demás queda en no-op.
      ph = null;
    }
  })();

  return cargando;
}

/** Apaga y borra lo que PostHog haya dejado en el navegador. */
export function desactivar(): void {
  try {
    // El orden importa y está en la doc del propio SDK: `reset()` limpia el
    // consentimiento y devuelve la instancia a su estado por defecto, que acá
    // es "opted in". Al revés, el opt-out se deshacía solo y el SDK seguía
    // midiendo por su cuenta después de que el usuario dijera que no.
    ph?.reset();
    ph?.opt_out_capturing();
  } catch {
    // Nada que hacer si el SDK ya está roto: el objetivo es que deje de medir,
    // y sin instancia usable eso ya se cumple.
  }
  ph = null;
  // Sin esto, `activar()` devolvía la promesa ya resuelta del primer arranque
  // y no volvía a asignar `ph` nunca.
  cargando = null;
}

/** Si ya dijo que sí en una visita anterior, arranca sin volver a preguntar. */
export async function activarSiConsintio(): Promise<void> {
  if (leerConsentimiento() === "si") await activar();
}

export function track<E extends EventoNombre>(evento: E, props: EventoProps[E]): void {
  if (!ph) return;
  try {
    ph.capture(evento, limpiar(props as Record<string, unknown>));
  } catch {
    // Medir no puede tumbar la página que mide.
  }
}

/** Una página vista, con la ruta ya sin idioma y sin uuid.
 *
 * Separar el idioma del camino es lo que hace comparable `/es/nueva` con
 * `/en/nueva` en vez de dejarlos como dos páginas distintas. No valida el
 * segmento contra `LOCALES` a propósito: esto corre en el arranque de cada
 * visita y no vale la pena arrastrar los tres diccionarios al bundle inicial
 * para chequear tres cadenas. Sólo existen /es, /en y /pt — cualquier otra
 * cosa es 404 y no llega hasta acá. */
export function capturarPagina(href: string): void {
  if (!ph || typeof window === "undefined") return;
  try {
    const { pathname } = new URL(href, window.location.origin);
    const partes = pathname.split("/").filter(Boolean);
    const conIdioma = partes[0]?.length === 2;
    track("pagina_vista", {
      locale: conIdioma ? partes[0] : "",
      ruta: "/" + (conIdioma ? partes.slice(1) : partes).join("/"),
    });
  } catch {
    // Una URL que no parsea no vale una excepción en el arranque.
  }
}

/** Ata los eventos a la cuenta por su id interno.
 *
 * Nunca el email: la política dice, literal, que no se lo mandamos. */
/** Al cerrar sesión: cortar el hilo entre la cuenta que se va y lo que haga
 *  después el próximo que use este navegador.
 *
 *  No toca el consentimiento —quien dijo que sí lo sigue diciendo—: `reset()`
 *  devuelve la instancia a su estado por defecto, que acá es medir. */
export function olvidarIdentidad(): void {
  if (!ph) return;
  try {
    ph.reset();
  } catch {
    // Ver `track`.
  }
}

export function identificar(accountId: number | string): void {
  if (!ph) return;
  try {
    ph.identify(String(accountId));
  } catch {
    // Ver `track`.
  }
}
