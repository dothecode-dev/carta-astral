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
  login: { provider: "google" | "apple" | "email" };
  /** Calculó su rueda. `con_sesion: false` es el visitante frío que entró
   *  por la home o por una nota y llegó a ver algo suyo sin registrarse: es el
   *  primer escalón del embudo que antes empezaba directamente en el login. */
  carta_calculada: { con_sesion: boolean };
  /** Vio su rueda sin cuenta y apretó para leer la interpretación, o sea que
   *  la puerta del registro aparece recién acá. La distancia entre este evento
   *  y `login` es lo que mide cuánta gente se cae en esa puerta. */
  lectura_pedida_sin_cuenta: Record<string, never>;
  /** `desde` distingue al que llenó el formulario ya con sesión del que venía
   *  del preview anónimo: son dos costos de adquisición distintos. */
  carta_creada: { desde: "formulario" | "preview" };
  /** Apretó el botón de leer. Se emite en el CLICK, no al terminar.
   *
   *  `interpretacion_generada` (abajo) no alcanza para saber cuánta gente
   *  pidió una lectura: se emite del lado del cliente cuando el sondeo
   *  termina, y el informe completo tarda unos seis minutos — quien cierra la
   *  pestaña, cambia de app o pierde la red no lo dispara nunca. La distancia
   *  entre este evento y aquél es exactamente cuánta gente pide y no se queda
   *  a ver el resultado; sin él, ese abandono se ve igual que no haber
   *  apretado nunca.
   *
   *  Comprar el informe NO lo dispara: eso es `checkout_iniciado`. */
  interpretacion_pedida: { tier: "corto" | "largo" };
  /** Pidió una lectura y el backend no la arrancó.
   *
   *  Sin esto, quien choca contra un 402, un 429 o el cupo diario agotado se
   *  cuenta igual que quien abandonó la espera: dos problemas distintos, con
   *  arreglos opuestos —uno es de producto, el otro de paciencia—.
   *
   *  `sin_derecho` cubre los dos códigos del 402 (`sin_leer_breve` y
   *  `sin_leer_informe`): cuál de los dos ya lo dice `tier`. `red` es el
   *  `fetch` que ni siquiera llegó, y es el único que no deja rastro del lado
   *  del servidor. */
  interpretacion_rechazada: {
    tier: "corto" | "largo";
    motivo: "sin_derecho" | "cap_diario" | "en_curso" | "demasiados" | "red" | "fallo";
  };
  interpretacion_generada: { lang: string; tier: "corto" | "largo" };
  /** Qué ofrecía la carta cuando la persona la tuvo delante.
   *
   *  Es el denominador que faltaba: `/carta/[id]` es donde se decide todo, y
   *  medir sólo lo que se aprieta deja "creó su carta y no leyó nada" como una
   *  cifra que tapa tres situaciones —vio los dos botones y no quiso, no le
   *  quedaban lecturas breves, o ya tenía todo leído—.
   *
   *  `agotada` es el callejón: gastó las tres de por vida, no hay nada que
   *  traducir gratis y la lectura breve no se vende ni se repone, así que
   *  donde iba el botón hay un aviso. `no_se_ofrece` es que ese producto ya
   *  está leído para esta carta.
   *
   *  Se emite cuando los botones se muestran de verdad, no mientras corre la
   *  espera: quien vuelve a la pestaña con el informe escribiéndose ve el
   *  sistema solar y nunca tuvo la decisión delante. */
  acciones_carta_vistas: {
    breve: "disponible" | "agotada" | "no_se_ofrece";
    completo: "comprar" | "leer" | "no_se_ofrece";
  };
  carta_descargada: { formato: "pdf" | "imagen" };
  /** Apretó Comprar y se lo mandó a Stripe. La otra mitad del embudo de pago
   *  —que la plata haya entrado— la emite el backend desde el webhook
   *  (`compra_completada`), que es donde se sabe de verdad: quien paga y cierra
   *  la pestaña no vuelve a ejecutar nada de esta página.
   *
   *  `desde` separa las dos puertas de compra, que no valen lo mismo: en
   *  /precios se compra a secas, y dentro de una carta se compra el informe DE
   *  esa carta, después de haber leído la breve. */
  checkout_iniciado: { producto: string; desde: "precios" | "carta"; cupon?: string };
  /** Llegó con un cupón (por link o por el campo) y la página ya sabe si
   *  sirvió. `resultado` es `valido` o el motivo: es lo que separa «el cupón
   *  vendió» de «la gente lo intentó y estaba agotado». */
  cupon_aplicado: { codigo: string; resultado: string };
  /** Cuántos aceptan el banner. Sin esto no se sabe cuánto sesga el resto:
   *  si acepta el 40%, todos los números de arriba son el 40% de la verdad. */
  consentimiento: { decision: "si" | "no" };
  /** Alguien llegó a /entrar, haya terminado el login o no. Se dispara al
   *  MONTAR la pantalla, no al loguearse —eso ya lo cubre `login`—: es el
   *  denominador que faltaba para saber cuánta gente se da vuelta antes de
   *  intentarlo. El 08-09-2026 tres de seis visitas rebotaron en segundos y
   *  no quedó ningún rastro de qué vieron.
   *
   *  `next` es la ruta de destino que traía —la misma que ya validó
   *  `destinoSeguro`—, nunca datos personales. Se omite si no había destino. */
  entrar_visto: { next?: string };
  /** El acceso se cerró sin login: `blocked` es que ni siquiera se pudo
   *  intentar (falta el client id, viene mal formado, o un bloqueador de
   *  rastreadores no dejó cargar el script de Google); `failed` es que se
   *  intentó y el canje contra /api/session no sirvió. Sin esto, un botón
   *  que nunca aparece y un login que sale mal se ven igual que silencio. */
  login_no_disponible: { motivo: "blocked" | "failed" };
  /** Pidió el código de 6 dígitos por mail (RF15). Es el denominador de esta
   *  puerta, igual que `entrar_visto` lo es de la pantalla entera: sin esto
   *  no se sabe cuánta gente arranca el camino de mail antes de canjear. */
  codigo_pedido: Record<string, never>;
  /** Canjeó el código y entró. Específico de esta puerta —a diferencia de
   *  `login`, que es el evento del embudo compartido con Google/Apple— para
   *  poder medir la conversión de PEDIR a CANJEAR sin mezclarla con las
   *  otras dos puertas. Los dos se emiten juntos al canjear bien. */
  codigo_canjeado: Record<string, never>;
  /** Un pedido o un canje que no sirvió. `paso` distingue en cuál de los dos
   *  pasó; `motivo` es el mismo vocabulario de `login_no_disponible` pero
   *  más fino, porque acá el pedido y el canje son dos rutas separadas con
   *  fallos distintos: `invalido` es el 401 del canje (código incorrecto o
   *  vencido, nunca sale del pedido), `demasiados` el 429, `no_disponible`
   *  el 503/502, y `red` el `fetch` que ni siquiera volvió — el único que no
   *  deja rastro del lado del servidor. */
  codigo_fallido: {
    paso: "pedido" | "canje";
    motivo: "invalido" | "demasiados" | "no_disponible" | "red";
  };
};

export type EventoNombre = keyof EventoProps;
