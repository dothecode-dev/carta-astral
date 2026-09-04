/** La lista cerrada de eventos de la web.
 *
 * Es un tipo, no una convención: mandar un evento que no esté acá no compila.
 * La app RN hace lo mismo (`src/telemetry/index.ts`) y por la misma razón —
 * con nombres libres, en tres meses hay `carta_creada`, `chart_created` y
 * `crear_carta` midiendo lo mismo y ningún embudo cierra.
 *
 * No hay autocapture en ninguna parte del sitio: `/nueva` muestra el lugar de
 * nacimiento en el buscador y `/carta` muestra el nombre, y el texto del
 * elemento clickeado es justo lo que autocapture manda. La política promete que
 * eso nunca sale, así que la única puerta de salida es esta lista.
 */

/** Props de cada evento. Sin `any`: el que agrega un evento define qué manda. */
export type EventoProps = {
  /** El que responde "¿cuánta gente entra y de dónde?". `ruta` es el patrón,
   *  no la URL: `/carta/[id]` y nunca el uuid, que identifica a una persona.
   *
   *  Cubre además la carta de ejemplo y cada nota del CMS, porque el slug ya
   *  viaja en la ruta: no hacen falta eventos propios para eso. */
  pagina_vista: { locale: string; ruta: string };
  login: { provider: "google" | "apple" };
  carta_creada: Record<string, never>;
  interpretacion_generada: { lang: string; tier: "corto" | "largo" };
  carta_descargada: { formato: "pdf" | "imagen" };
  /** Apretó Comprar y se lo mandó a Stripe. La otra mitad del embudo de pago
   *  —que la plata haya entrado— la emite el backend desde el webhook
   *  (`compra_completada`), que es donde se sabe de verdad: quien paga y cierra
   *  la pestaña no vuelve a ejecutar nada de esta página.
   *
   *  `desde` separa las dos puertas de compra, que no valen lo mismo: en
   *  /precios se compra a secas, y dentro de una carta se compra el informe DE
   *  esa carta, después de haber leído la breve. */
  checkout_iniciado: { producto: string; desde: "precios" | "carta" };
  /** Cuántos aceptan el banner. Sin esto no se sabe cuánto sesga el resto:
   *  si acepta el 40%, todos los números de arriba son el 40% de la verdad. */
  consentimiento: { decision: "si" | "no" };
};

export type EventoNombre = keyof EventoProps;
