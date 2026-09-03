// Diccionarios de la web. Sin librería: son tres idiomas y un puñado de claves,
// y next-intl traería un middleware y un provider para resolver un objeto.

export const LOCALES = ["es", "en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

/** El idioma que pide el navegador, si es uno de los tres; si no, el de por defecto.
 *
 * Sin `@formatjs/intl-localematcher` ni `negotiator`, que es lo que sugiere la
 * doc de Next: para tres idiomas sin variantes regionales el matcheo es por
 * prefijo, y dos dependencias para eso salen más caras que estas líneas.
 *
 * `Accept-Language` viene como `pt-BR,pt;q=0.9,en;q=0.8`: cada entrada con su
 * peso, sin garantía de venir ordenada. Se ordena por `q` y gana el primero que
 * sea uno de los nuestros — `pt-BR` cuenta como `pt`. Un `q=0` significa
 * "explícitamente no", así que esa entrada se descarta. */
export function negociarIdioma(acceptLanguage: string | null | undefined): Locale {
  if (!acceptLanguage) return DEFAULT_LOCALE;

  const preferencias = acceptLanguage
    .split(",")
    .map((entrada) => {
      const [etiqueta, ...parametros] = entrada.trim().split(";");
      const q = parametros
        .map((p) => /^\s*q=([\d.]+)\s*$/.exec(p))
        .find((m) => m !== null)?.[1];
      const peso = q === undefined ? 1 : Number.parseFloat(q);
      return { idioma: etiqueta.trim().toLowerCase().split("-")[0], peso };
    })
    .filter((p) => p.idioma !== "" && Number.isFinite(p.peso) && p.peso > 0)
    // `sort` de JS no es estable entre pesos iguales en todos los motores, pero
    // sí lo es en V8, que es el único que corre esto. El orden de aparición
    // desempata, que es lo que dice el RFC 9110.
    .sort((a, b) => b.peso - a.peso);

  // Un `for` y no un `find`: el estrechamiento de `isLocale` no sobrevive al
  // `?.idioma` de un `find`, y castear para taparlo sería peor.
  for (const { idioma } of preferencias) {
    if (isLocale(idioma)) return idioma;
  }
  return DEFAULT_LOCALE;
}

/** El segmento de la sección de notas, traducido.
 *
 * La palabra en la URL es una señal de idioma para los buscadores, y evita que
 * `/en/notas` compita con `/es/notas` por la misma consulta. La ruta que lo
 * sirve es `app/[locale]/[section]`, que sólo acepta estos pares: cualquier
 * otro valor del segmento es 404. */
export const NOTES_SLUG: Record<Locale, string> = {
  es: "notas",
  en: "notes",
  pt: "notas",
};

/** Si `section` es la sección de notas de ese idioma. Falso para la de otro:
 * `/en/notas` no existe, existe `/en/notes`. */
export function isNotesSection(locale: Locale, section: string): boolean {
  return NOTES_SLUG[locale] === section;
}

/** Locale de Intl para fechas y horas, no para el contenido. */
export const INTL_LOCALE: Record<Locale, string> = {
  es: "es-AR",
  en: "en-US",
  pt: "pt-BR",
};

/** Nombres de los cuerpos celestes. Los glifos no se traducen: son notación. */
export const PLANET_NAMES: Record<Locale, string[]> = {
  es: ["Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno", "Urano", "Neptuno", "Plutón"],
  en: ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"],
  pt: ["Sol", "Lua", "Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno", "Plutão"],
};

/** El backend nombra los cuerpos en inglés; la tabla los muestra traducidos. */
/** El motor nombra los aspectos en inglés; la tabla los muestra traducidos. */
export const ASPECT_NAMES: Record<Locale, Record<string, string>> = {
  es: { conjunction: "Conjunción", opposition: "Oposición", trine: "Trígono",
        square: "Cuadratura", sextile: "Sextil", quintile: "Quintil" },
  en: { conjunction: "Conjunction", opposition: "Opposition", trine: "Trine",
        square: "Square", sextile: "Sextile", quintile: "Quintile" },
  pt: { conjunction: "Conjunção", opposition: "Oposição", trine: "Trígono",
        square: "Quadratura", sextile: "Sextil", quintile: "Quintil" },
};

/** El angulo exacto de cada aspecto, para explicar de donde sale. */
export const ASPECT_ANGLE: Record<string, number> = {
  conjunction: 0, sextile: 60, quintile: 72, square: 90, trine: 120, quincunx: 150, opposition: 180,
};

/**
 * Que significa cada aspecto, en una frase.
 *
 * Mucha gente llega a su carta sin saber leer una matriz de aspectos. La celda
 * sola no ensena nada: dice que hay un sextil entre la Luna y el Ascendente y
 * deja a la persona igual que antes.
 */
export const ASPECT_MEANING: Record<Locale, Record<string, string>> = {
  es: {
    conjunction: "Dos cuerpos en el mismo punto del cielo. No dialogan: se funden y actúan como uno solo, para bien y para mal.",
    opposition: "Enfrentados, cada uno en una punta de la carta. Piden equilibrio, y mientras no lo encuentran se turnan para mandar.",
    square: "Fricción entre dos cuerpos que se estorban. Es incómoda y es motor: casi todo lo que una persona construye sale de sus cuadraturas.",
    trine: "Fluye sin esfuerzo, y por eso se nota poco. Es talento que ya está: el riesgo es no usarlo nunca porque nunca dolió.",
    sextile: "Una ocasión, no un regalo. Funciona cuando la persona hace algo con ella; si no, pasa de largo sin avisar.",
    quintile: "Un ángulo menor, ligado a lo creativo. Se lee con cuidado: su efecto es sutil y no todos los astrólogos lo usan.",
    quincunx: "Dos cuerpos que no se ven entre sí y tienen que convivir igual. Se siente como un ajuste que nunca termina de cerrar.",
  },
  en: {
    conjunction: "Two bodies at the same point in the sky. They don't talk: they merge and act as one, for better and for worse.",
    opposition: "Facing each other from opposite ends of the chart. They ask for balance, and until they find it they take turns running the show.",
    square: "Friction between two bodies that get in each other's way. It's uncomfortable and it's an engine: most of what a person builds comes out of their squares.",
    trine: "It flows without effort, which is why it goes unnoticed. It's talent already there: the risk is never using it because it never hurt.",
    sextile: "An opening, not a gift. It works when the person does something with it; otherwise it passes by without a word.",
    quintile: "A minor angle, tied to the creative. Read it carefully: its effect is subtle and not every astrologer uses it.",
    quincunx: "Two bodies that can't see each other and have to live together anyway. It feels like an adjustment that never quite settles.",
  },
  pt: {
    conjunction: "Dois corpos no mesmo ponto do céu. Não dialogam: se fundem e agem como um só, para o bem e para o mal.",
    opposition: "Frente a frente, cada um numa ponta do mapa. Pedem equilíbrio, e enquanto não o encontram se revezam no comando.",
    square: "Atrito entre dois corpos que se atrapalham. É incômodo e é motor: quase tudo o que uma pessoa constrói sai das suas quadraturas.",
    trine: "Flui sem esforço, e por isso quase não se nota. É talento que já está ali: o risco é nunca usá-lo porque nunca doeu.",
    sextile: "Uma ocasião, não um presente. Funciona quando a pessoa faz algo com ela; se não, passa direto sem avisar.",
    quintile: "Um ângulo menor, ligado ao criativo. Lê-se com cuidado: seu efeito é sutil e nem todo astrólogo o usa.",
    quincunx: "Dois corpos que não se enxergam e precisam conviver assim mesmo. Sente-se como um ajuste que nunca fecha de todo.",
  },
};

/** Los mismos glifos que usa la app (src/astro/glyphs.ts). */
/**
 * Los glifos de los cuerpos. Estaba repetida en tres archivos y se
 * desincronizo: al pasar la rueda a catorce cuerpos, la tabla de la carta de
 * ejemplo se quedo con diez y los cuatro nuevos salieron sin simbolo.
 */
export const PLANET_GLYPHS: Record<string, string> = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
  Chiron: "⚷", True_North_Lunar_Node: "☊", True_South_Lunar_Node: "☋", Mean_Lilith: "⚸",
};

export const ASPECT_GLYPHS: Record<string, string> = {
  conjunction: "☌", opposition: "☍", trine: "△", square: "□", sextile: "✶",
};

/**
 * Los cuerpos que la carta lista pero la rueda no dibuja.
 *
 * El backend los devuelve con el nombre del motor y salían así en la tabla:
 * "True South Lunar Node" en medio de una carta en español.
 */
const EXTRA_BODIES: Record<Locale, Record<string, string>> = {
  es: {
    Chiron: "Quirón",
    Mean_Lilith: "Lilith media",
    True_North_Lunar_Node: "Nodo Norte",
    True_South_Lunar_Node: "Nodo Sur",
  },
  en: {
    Chiron: "Chiron",
    Mean_Lilith: "Mean Lilith",
    True_North_Lunar_Node: "North Node",
    True_South_Lunar_Node: "South Node",
  },
  pt: {
    Chiron: "Quíron",
    Mean_Lilith: "Lilith média",
    True_North_Lunar_Node: "Nodo Norte",
    True_South_Lunar_Node: "Nodo Sul",
  },
};

export const PLANET_NAME_BY_KEY: Record<Locale, Record<string, string>> = {
  es: { ...Object.fromEntries(PLANET_NAMES.en.map((k, i) => [k, PLANET_NAMES.es[i]])), ...EXTRA_BODIES.es },
  en: { ...Object.fromEntries(PLANET_NAMES.en.map((k) => [k, k])), ...EXTRA_BODIES.en },
  pt: { ...Object.fromEntries(PLANET_NAMES.en.map((k, i) => [k, PLANET_NAMES.pt[i]])), ...EXTRA_BODIES.pt },
};

export type Dict = {
  meta: { title: string; description: string };
  nav: { example: string; notes: string; precios: string };
  theme: { night: string; day: string; label: string };
  rail: { eyebrow: string; note: string };
  hero: { title: string; lede: string; ledeStrong: string; cta: string; ctaSecondary: string; wheelAlt: string };
  flow: {
    eyebrow: string;
    title: string;
    steps: { label: string; title: string; body: string }[];
  };
  notes: {
    eyebrow: string;
    title: string;
    lede: string;
    /** Cuando el idioma todavía no tiene ninguna nota publicada. */
    empty: string;
    back: string;
    /** "3 de agosto de 2026" se arma con `Intl`; esto es lo que va antes. */
    publishedOn: string;
  };
  privacy: { eyebrow: string; title: string; points: { strong: string; rest: string }[]; link: string };
  pricing: {
    eyebrow: string;
    title: string;
    /** El único precio decidido hoy: el informe completo, comprado suelto. */
    price: string;
    priceNote: string;
    terms: { label: string; value: string; free?: boolean }[];
    note: string;
    /** A la página de precios. La sección no tenía ni un enlace: la tabla
     *  terminaba en una nota y ahí se cortaba el camino a comprar. */
    cta: string;
  };
  faq: { eyebrow: string; title: string; items: { q: string; a: string }[] };
  /** El cierre de la home. Antes anunciaba las apps de las tiendas con un
   *  «Próximamente»; la app no se está construyendo, así que el último empujón
   *  de la página lleva al formulario de carta nueva, que es el producto real. */
  cierre: {
    eyebrow: string;
    title: string;
    note: string;
    cta: string;
  };
  foot: { brand: string; privacy: string; terms: string; contact: string };
  consent: { text: string; accept: string; reject: string; more: string; footLink: string };
  precios: {
    title: string;
    lede: string;
    /** Nombre de cada producto, por código del catálogo. */
    nombre: Record<string, string>;
    /** Qué incluye cada producto, por código. */
    detalle: Record<string, string>;
    /** Precio por unidad en los packs. Lleva "{precio}". */
    porUnidad: string;
    comprar: string;
    abriendo: string;
    fallo: string;
    /** Si el catálogo no se pudo cargar. */
    sinCatalogo: string;
    nota: string;
    /**
     * La lectura breve, arriba de todo lo que se cobra.
     *
     * No sale del catálogo público —vale 0 y el backend no la lista—, así que
     * si no se escribe acá no aparece en ningún lado: quien llegaba a esta
     * página desde afuera creía que el piso para probar ASTRA eran US$ 29.
     */
    gratisNombre: string;
    gratisPrecio: string;
    gratisDetalle: string;
    /** Distintivo del pack que conviene mirar primero. */
    recomendado: string;
    /** A la muestra de lectura: nadie compra 6.000 palabras a ciegas. */
    verEjemplo: string;
  };
  auth: {
    navEnter: string;
    title: string;
    lede: string;
    loading: string;
    blocked: string;
    failed: string;
    legal: string;
    /**
     * Título de lo que la cuenta puede usar ahora mismo.
     *
     * El bloque de derechos no tenía ninguno: aparecía suelto bajo el mail, en
     * gris, y su único enlace era "Ver precios" —o sea, comprar más—. Lo que
     * alguien busca al entrar es qué tiene y dónde usarlo, y ninguna de las dos
     * cosas estaba escrita.
     */
    listoTitle: string;
    /** El paso siguiente cuando ya hay cartas donde gastar el derecho. */
    listoUsar: string;
    /** El paso siguiente cuando todavía no hay ninguna carta. */
    listoUsarSinCartas: string;
    /** Derecho de lectura breve con más de una disponible. Lleva "{n}". */
    derechosBreve: string;
    /** El mismo derecho con exactamente una disponible: singular, no "{n}" a secas. */
    derechosBreveUno: string;
    /** Derecho de informe completo con más de uno disponible (por ejemplo, un pack). Lleva "{n}". */
    derechosInforme: string;
    /** El mismo derecho con exactamente uno disponible: singular. */
    derechosInformeUno: string;
    /** Cuando la cuenta no tiene ningún derecho activo: en vez de mostrar "0", ofrece comprar. */
    sinDerechos: string;
    /** CTA de esa oferta: comprar el informe completo (la única compra que existe hoy). */
    comprarInforme: string;
    /** Nota bajo esa CTA. */
    comprarNota: string;
    /** Con qué mail entró la persona. Lleva "{email}". */
    conectadoComo: string;
    /** Cuando la cuenta no tiene mail (se puede entrar con Apple ocultándolo). */
    conectadoSinMail: string;
    /** Título de la lista de compras. */
    comprasTitle: string;
    /** Cuando todavía no compró nada. */
    comprasEmpty: string;
    /** Una compra pagada cuyo webhook todavía no acreditó. */
    compraPendiente: string;
    /** Enlace a la página de precios desde la cuenta. */
    verPrecios: string;
    account: string;
    signOut: string;
    chartsTitle: string;
    chartsEmpty: string;
    chartsEmptyCta: string;
    unnamedChart: string;
    readIn: string;
    settings: string;
    dangerTitle: string;
    deleteChartsTitle: string;
    deleteChartsBody: string;
    deleteChartsConfirm: string;
    deleteAccountTitle: string;
    deleteAccountBody: string;
    deleteAccountConfirm: string;
    confirmHint: string;
    cancel: string;
    working: string;
  };
  chart: {
    back: string;
    noWheel: string;
    noWheelBody: string;
    incomplete: string;
    /** Botón de la lectura breve gratis (tier "corto"). */
    interpretBreve: string;
    /** Nota bajo el botón de la breve. Lleva `{n}`: cuántas lecturas breves gratis quedan. */
    interpretBreveNota: string;
    /** Botón del informe completo pago (tier "largo"). */
    interpretCompleto: string;
    /**
     * Enlace a los Términos de uso desde el bloque de compra.
     *
     * El pie de la lectura dejó de anunciar que la escribe una IA (02-09-2026):
     * esa explicación vive en los Términos, que la dan entera. Este enlace
     * existe para que esté a un clic ANTES de pagar, que es el único momento
     * donde callarlo sale caro.
     */
    comoSeEscribe: string;
    /**
     * Botón del informe cuando la cuenta YA tiene el derecho (compró un pack,
     * o pagó y volvió). Mandarla a pagar otra vez sería cobrarle dos veces.
     */
    interpretCompletoConDerecho: string;
    /** Cuando el pago no se pudo abrir: el problema es nuestro, no de quien compra. */
    compraFallo: string;
    /** Nota bajo el botón del completo: precio y qué trae, con hora conocida (ocho secciones). */
    interpretCompletoNota: string;
    /**
     * Misma nota, pero para una carta sin hora de nacimiento (RF12): el
     * informe sale con siete secciones, sin la de casas. Sin esta variante,
     * el botón prometía ocho secciones y `noTimeWarning`, debajo, admitía
     * que salían siete — las dos a la vista al mismo tiempo.
     */
    interpretCompletoNotaSinHora: string;
    /**
     * Nota bajo el botón del completo cuando la cuenta YA tiene el derecho.
     *
     * Sin esta rama la nota sólo miraba el idioma y la hora, así que a quien
     * había comprado un pack de cinco el botón le decía "Leer el informe
     * completo" y la línea de abajo "US$ 29 · ocho secciones": el precio de
     * algo que ya estaba pago, en la misma pantalla y a dos centímetros. Nadie
     * aprieta un botón que parece que va a cobrarle de nuevo.
     */
    interpretCompletoNotaConDerecho: string;
    /** La misma, para una carta sin hora: siete secciones (ver `...SinHora`). */
    interpretCompletoNotaConDerechoSinHora: string;
    /**
     * Cuánto queda del pack, debajo de la nota anterior. Sólo se muestra con
     * más de uno, así que el plural nunca queda mal: con el último informe la
     * frase sobra —lo que importa es que ya está pago—.
     */
    interpretCompletoSaldo: string;
    /**
     * Nota de cualquiera de los dos botones cuando ESE tier ya está completo
     * en otro idioma: traducirlo no cuesta (el backend lo resuelve sin tocar
     * el ledger), así que reemplaza a `interpretBreveNota`/
     * `interpretCompletoNota` — decir el precio ahí sería mentir.
     */
    interpretFreeLang: string;
    interpreting: string;
    readAgain: string;
    /**
     * 503 con code "cap_diario": el cupo de lecturas breves gratis del día se
     * agotó. No es una caída, y decirle a la persona "no pudimos generar la
     * lectura" le hace creer que algo se rompió y que reintentar sirve.
     */
    capDiario: string;
    /** 429: demasiados intentos seguidos desde la misma cuenta o IP. */
    demasiados: string;
    /** 402 con code "sin_leer_breve": se acabó el lote de lecturas breves gratis. */
    sinLeerBreve: string;
    /** 402 con code "sin_leer_informe": el informe completo todavía no está comprado. */
    sinLeerInforme: string;
    /** 402 con un code no reconocido: mensaje genérico. */
    sinDerecho: string;
    failed: string;
    /** 409: ya hay una generación en curso para esta carta en otro idioma. */
    generationInProgress: string;
    columns: { body: string; position: string; house: string };
    houses: string;
    aspects: string;
    axisNames: { AC: string; MC: string };
    aspectColumns: { pair: string; aspect: string; orb: string };
    show: string;
    hide: string;
    waitTitle: string;
    /** Texto de espera mientras se genera el informe completo (ocho secciones). */
    waitBody: string;
    /**
     * Texto de espera para la lectura breve: una sola llamada al modelo, no
     * "ocho secciones". Sin esto, los primeros ~5 segundos de la ÚNICA
     * espera de la breve (antes de que llegue el primer sondeo de progreso)
     * mostraban `waitBody`, que describe un informe que no se está
     * escribiendo.
     */
    waitBodyBreve: string;
    /** Con `{hechas}` y `{total}`: cuántas de las secciones de este tier ya están. */
    waitProgress: string;
    /**
     * La frase que acompaña toda la espera, como segundo renglón. Nació el
     * 02-08-2026 con la espera "que se parece a la app" y se perdió el 28-08,
     * cuando la lectura de medio minuto pasó a ser un informe de varios
     * minutos y el copy se volvió puramente operativo.
     *
     * Va aparte de `waitBody` a propósito: ese párrafo se reemplaza por
     * `waitProgress` en cuanto llega el primer sondeo (~5 s), así que una
     * frase puesta ahí se vería cinco segundos de los seis minutos que dura
     * el informe completo.
     */
    waitColor: string;
    /** RF12: aviso previo, antes de gastar el derecho, si la carta no tiene hora. */
    noTimeWarning: string;
    reading: string;
    /** Encabezado del pie que muestra qué trae el informe completo (Task 15). */
    resumenTitulo: string;
    /** Cuánto falta de cada sección todavía sin comprar. Lleva `{n}`: palabras. */
    resumenRestante: string;
    /** Cierre del pie, invitando a comprar el informe completo. */
    resumenCta: string;
  };
  /** La pantalla de vuelta del pago (`STRIPE_SUCCESS_URL`). */
  compra: {
    /** Mientras se espera la confirmación del pago, que tarda segundos. */
    title: string;
    body: string;
    /** Si esa confirmación no llegó en 45 segundos. No es un error: es la
     *  verdad —el pago se hizo— y dónde seguir. */
    demoraTitle: string;
    demoraBody: string;
    /** Cuando se llega sin `checkout_id`: a mano, o con un link guardado. */
    sinDatoTitle: string;
    sinDatoBody: string;
    irACuenta: string;
  };
  share: {
    /** Rótulo de la portada del documento y título de la tabla de posiciones. */
    chartEyebrow: string;
    positionsTitle: string;
    /** Encabezado del bloque: los tres botones son archivos para llevarse. */
    downloadsTitle: string;
    pdf: string;
    pdfWithReading: string;
    /** Cuando la lectura está escrita en otro idioma; `{lang}` lo nombra. */
    pdfWithReadingIn: string;
    image: string;
    /** La línea chica de cada botón: qué trae el archivo, no qué hace el botón. */
    pdfHint: string;
    pdfWithReadingHint: string;
    imageHint: string;
    working: string;
    failed: string;
    /** Bajo la marca, en la portada del documento. */
    tagline: string;
    madeWith: string;
    langNames: { es: string; en: string; pt: string };
  };
  newChart: {
    navNew: string;
    title: string;
    lede: string;
    name: string;
    namePlaceholder: string;
    nameHint: string;
    date: string;
    time: string;
    timeUnknown: string;
    timeUnknownHint: string;
    place: string;
    placePlaceholder: string;
    searching: string;
    noPlaces: string;
    changePlace: string;
    submit: string;
    submitting: string;
    needPlace: string;
    needDate: string;
    badDate: string;
    failed: string;
    /** 402 con code "sin_leer_breve": no hay lectura breve gratis disponible para esta carta nueva. */
    sinLeerBreve: string;
  };
};

const es: Dict = {
  meta: {
    title: "ASTRA — cartas astrales",
    description:
      "Tu carta natal calculada con efemérides reales y leída en tu idioma. Directo en el navegador, sin instalar nada.",
  },
  nav: { example: "Carta de ejemplo", notes: "Notas", precios: "Precios" },
  theme: { night: "Noche", day: "Día", label: "Luz de la página" },
  rail: {
    eyebrow: "Efeméride — ahora",
    note: "Posiciones geocéntricas del momento en que abriste la página. Se recalculan solas.",
  },
  hero: {
    title: "Así está el cielo mientras leés esto.",
    lede:
      "La rueda no es una ilustración: son las posiciones reales de este instante, calculadas con las mismas efemérides que ASTRA usa para tu carta natal.",
    ledeStrong: "Poné tu fecha, hora y lugar de nacimiento y vas a ver la tuya.",
    cta: "Ver mi carta natal",
    ctaSecondary: "Ver una carta de ejemplo",
    wheelAlt: "Rueda con las posiciones planetarias del momento actual",
  },
  flow: {
    eyebrow: "De tu fecha al texto",
    title: "Tres pasos entre tu nacimiento y tu texto.",
    steps: [
      {
        label: "Tus datos",
        title: "Fecha, hora y lugar",
        body:
          "El lugar se busca sobre un padrón de 234.000 localidades y trae su huso horario, así la hora de nacimiento cae donde tiene que caer.",
      },
      {
        label: "El cálculo",
        title: "Efemérides, no aproximaciones",
        body:
          "Posiciones planetarias, casas y aspectos salen de Swiss Ephemeris. El mismo motor que usan los astrólogos profesionales.",
      },
      {
        label: "El texto",
        title: "Tu carta, en tu idioma",
        body:
          "El texto se escribe sobre la carta ya calculada, y podés leerlo en español, inglés o portugués sin volver a empezar.",
      },
    ],
  },
  notes: {
    eyebrow: "Notas",
    title: "Qué significa cada cosa que ves en tu carta.",
    lede: "Astrología explicada sin misticismo: qué mide cada pieza de la carta y qué no.",
    empty: "Todavía no hay notas publicadas en español. Están en camino.",
    back: "Todas las notas",
    publishedOn: "Publicada el",
  },
  privacy: {
    eyebrow: "Privacidad",
    title: "Tus datos de nacimiento no salen de tu cuenta.",
    points: [
      {
        strong: "Se usan para una sola cosa.",
        rest: "Tu fecha, tu hora y el lugar donde naciste sirven para calcular tu carta. Nada más.",
      },
      {
        strong: "No vendemos ni publicamos nada tuyo.",
        rest: "Ni tus cartas, ni tus lecturas, ni tu email. Tampoco mostramos publicidad.",
      },
      {
        strong: "Borrar es borrar.",
        rest: "Podés eliminar una carta o toda tu cuenta desde acá, y no queda copia.",
      },
    ],
    link: "Leer la política completa →",
  },
  pricing: {
    eyebrow: "Precios",
    title: "Tus primeras tres lecturas breves son gratis.\nEl informe completo se compra aparte.",
    price: "US$ 29",
    priceNote: "el informe completo de una carta: ocho secciones, unas 6.000 palabras",
    terms: [
      { label: "Tus primeras 3 lecturas breves", value: "Gratis", free: true },
      { label: "Informe completo de una carta", value: "US$ 29" },
      { label: "El mismo informe en otro idioma", value: "Sin costo", free: true },
      { label: "Packs de 3 o 5 informes", value: "Desde US$ 25 cada uno" },
      { label: "Vencimiento", value: "No vencen" },
    ],
    note: "Precios en dólares. Se paga directo en la web; el importe final puede incluir impuestos según tu país.",
    cta: "Ver todos los precios",
  },
  faq: {
    eyebrow: "Preguntas",
    title: "Lo que se pregunta todo el mundo antes de empezar.",
    items: [
      {
        q: "¿Necesito la hora exacta de nacimiento?",
        a: "Ayuda mucho: el Ascendente y las casas se corren un grado cada cuatro minutos. Podés cargar la carta sin hora, pero en ese caso no incluye casas, ni Ascendente, ni aspectos, y la posición de la Luna queda aproximada.",
      },
      {
        q: "¿En qué idiomas está?",
        a: "Español, inglés y portugués. Leer una carta que ya generaste en otro idioma no cuesta nada.",
      },
      {
        q: "¿El cálculo es serio o es un horóscopo?",
        a: "El cálculo es serio: Swiss Ephemeris, casas Placidus, zodíaco tropical, los mismos que usa un astrólogo profesional. Lo que leés se escribe sobre ese cálculo, y es para entretenimiento y autoconocimiento.",
      },
      {
        q: "¿Necesito crear una cuenta?",
        a: "Entrás con tu cuenta de Google. No hay contraseñas que recordar ni formulario que completar.",
      },
      {
        q: "¿Puedo hacer cartas de otras personas?",
        a: "Sí. Cada carta que guardás queda en tu cuenta con el nombre que le pongas, y podés borrarla cuando quieras.",
      },
      {
        q: "¿Qué pasa si borro mi cuenta?",
        a: "Se eliminan tus cartas, tus lecturas y lo que tengas disponible para leer, sin copia de respaldo. Es definitivo y lo hacés vos desde tu cuenta.",
      },
    ],
  },
  cierre: {
    eyebrow: "Empezar",
    title: "Empezá por la tuya.",
    note: "En el navegador, sin instalar nada. Tu primera lectura breve no cuesta nada.",
    cta: "Ver mi carta natal",
  },
  chart: {
    back: "← Tus cartas",
    noWheel: "Esta carta no tiene rueda.",
    noWheelBody: "Se cargó sin hora de nacimiento, así que no hay Ascendente ni casas para orientarla. Las posiciones planetarias sí están.",
    incomplete: "Falta algún cuerpo: su efeméride no cubre esa fecha.",
    interpretBreve: "Leer la lectura breve",
    interpretBreveNota: "Gratis. Te quedan {n}.",
    interpretCompleto: "Comprar el informe completo",
    comoSeEscribe: "Cómo se escribe tu lectura",
    interpretCompletoConDerecho: "Leer el informe completo",
    compraFallo: "No pudimos abrir el pago. Probá de nuevo en un momento.",
    interpretCompletoNota: "US$ 29 · ocho secciones",
    interpretCompletoNotaSinHora: "US$ 29 · siete secciones",
    interpretCompletoNotaConDerecho: "Ya lo tenés pago · ocho secciones",
    interpretCompletoNotaConDerechoSinHora: "Ya lo tenés pago · siete secciones",
    interpretCompletoSaldo: "Después de este te quedan {n}.",
    interpretFreeLang: "Sin costo: ya lo leíste en otro idioma.",
    interpreting: "Escribiendo tu lectura…",
    readAgain: "Ver la lectura",
    capDiario: "Por hoy se agotaron las lecturas breves gratis. Volvé mañana, o leé el informe completo.",
    demasiados: "Demasiados intentos seguidos. Esperá un momento y probá de nuevo.",
    sinLeerBreve: "Te quedaste sin lecturas breves gratis.",
    sinLeerInforme: "Todavía no compraste el informe completo.",
    sinDerecho: "No tenés esta lectura disponible.",
    failed: "No pudimos generar la lectura. Probá de nuevo en un rato.",
    generationInProgress:
      "Ya hay una generación en curso para esta carta en otro idioma. Esperá unos segundos y volvé a intentar.",
    columns: { body: "Cuerpo", position: "Posición", house: "Casa" },
    houses: "Casas",
    aspects: "Aspectos",
    axisNames: { AC: "Ascendente", MC: "Medio Cielo" },
    aspectColumns: { pair: "Entre", aspect: "Aspecto", orb: "Orbe" },
    show: "Ver",
    hide: "Ocultar",
    waitTitle: "Leyendo tu cielo",
    waitBody: "Estamos escribiendo tu informe, en ocho secciones. Cada una se piensa aparte, con tu carta entera delante: por eso demora unos seis minutos.",
    waitBodyBreve: "Estamos escribiendo tu lectura breve. Demora medio minuto.",
    waitProgress: "Vamos por la sección {hechas} de {total}.",
    waitColor: "Podés cerrar esta ventana. Acá no hay cartas prearmadas: cada sección se escribe para esta carta y sólo para ésta, y por eso puede demorar hasta seis minutos. Cuando esté, te espera en tu cuenta.",
    noTimeWarning: "Esta carta quedó sin hora de nacimiento: el informe sale con siete secciones, sin la de casas.",
    reading: "Tu lectura",
    resumenTitulo: "Esto trae el informe completo",
    resumenRestante: "+{n} palabras",
    resumenCta: "Comprá el informe completo para leerlas todas.",
  },
  compra: {
    title: "Listo, gracias",
    body: "Estamos confirmando tu pago. Tarda unos segundos y te llevamos solos a lo que compraste.",
    demoraTitle: "Tu pago se hizo",
    demoraBody: "La confirmación está tardando más de lo normal. No hace falta que pagues de nuevo: en cuanto llegue, lo vas a encontrar en tu cuenta. Si en unos minutos no aparece, escribinos a info@astraguia.com.",
    sinDatoTitle: "Gracias por tu compra",
    sinDatoBody: "Lo que compraste te espera en tu cuenta.",
    irACuenta: "Ir a mi cuenta",
  },
  share: {
    chartEyebrow: "Carta natal",
    positionsTitle: "Posiciones",
    downloadsTitle: "Descargas",
    pdf: "PDF de la carta",
    pdfWithReading: "PDF completo",
    pdfWithReadingIn: "PDF completo (en {lang})",
    image: "La carta como imagen",
    pdfHint: "Rueda, posiciones y aspectos",
    pdfWithReadingHint: "La carta y tu lectura, listo para imprimir",
    imageHint: "1080×1920, para historias",
    working: "Preparando…",
    failed: "No pudimos preparar el archivo. Probá de nuevo.",
    tagline: "Tu carta natal",
    madeWith: "Hecho con ASTRA",
    langNames: { es: "español", en: "inglés", pt: "portugués" },
  },
  newChart: {
    navNew: "Nueva carta",
    title: "Calculá tu carta.",
    lede: "Con la fecha, la hora y el lugar donde naciste.",
    name: "Nombre",
    namePlaceholder: "Para reconocerla después",
    nameHint: "Opcional. No se usa para calcular nada.",
    date: "Fecha de nacimiento",
    time: "Hora",
    timeUnknown: "No sé la hora",
    timeUnknownHint: "Sin hora no hay Ascendente, ni casas, ni aspectos, y la Luna queda aproximada.",
    place: "Lugar de nacimiento",
    placePlaceholder: "Ciudad o localidad",
    searching: "Buscando…",
    noPlaces: "No encontramos ese lugar. Probá con la ciudad más cercana.",
    changePlace: "Cambiar",
    submit: "Calcular mi carta",
    submitting: "Calculando…",
    needPlace: "Elegí el lugar de nacimiento.",
    needDate: "Falta la fecha de nacimiento.",
    badDate: "Revisá la fecha: tiene que ser posterior a 1800 y no puede estar en el futuro.",
    failed: "No pudimos calcular la carta. Revisá los datos y probá de nuevo.",
    sinLeerBreve: "Ya usaste tus lecturas breves gratis.",
  },
  foot: { brand: "ASTRA · Cartas astrales", privacy: "Privacidad", terms: "Términos", contact: "Contacto" },
  consent: {
    text: "Nos ayuda saber cuánta gente entra y qué páginas mira. Sin publicidad, sin vender datos y sin tu nombre ni tus datos de nacimiento.",
    accept: "Aceptar",
    reject: "No, gracias",
    more: "Cómo tratamos tus datos",
    footLink: "Analítica",
  },
  precios: {
    title: "Elegí cómo querés leerte.",
    lede: "Comprás una vez y lo usás cuando quieras: los informes de un pack no vencen.",
    nombre: {
      informe_natal: "Informe completo",
      pack_3_natal: "Tres informes",
      pack_5_natal: "Cinco informes",
    },
    detalle: {
      informe_natal: "Tu carta natal interpretada en ocho secciones, unas 6.000 palabras. Se lee en la web y se descarga en PDF.",
      pack_3_natal: "Tres informes completos para usar en las cartas que elijas, cuando quieras.",
      pack_5_natal: "Cinco informes completos para usar en las cartas que elijas, cuando quieras.",
    },
    porUnidad: "{precio} cada uno",
    comprar: "Comprar",
    abriendo: "Abriendo el pago…",
    fallo: "No pudimos abrir el pago. Probá de nuevo.",
    sinCatalogo: "No pudimos cargar los precios. Volvé a intentar en un momento.",
    gratisNombre: "Lectura breve",
    gratisPrecio: "Gratis",
    gratisDetalle: "Tres por cuenta, sin tarjeta. Tu carta en unos párrafos.",
    recomendado: "El más elegido",
    verEjemplo: "Ver un ejemplo",
    nota: "Los informes que compres quedan en tu cuenta hasta que los uses. El pago lo procesa Stripe; el impuesto de tu país ya está incluido en el precio.",
  },
  auth: {
    navEnter: "Entrar",
    title: "Entrá a tu cuenta.",
    lede: "Tus cartas y tus lecturas quedan guardadas en tu cuenta.",
    loading: "Cargando…",
    blocked: "No pudimos cargar el acceso de Google. Suele pasar con bloqueadores de rastreadores: desactivalo para este sitio y recargá.",
    failed: "No pudimos iniciar sesión. Probá de nuevo.",
    legal: "Al entrar aceptás los términos y la política de privacidad.",
    listoTitle: "Listo para usar",
    listoUsar: "Elegí una carta para usarlo",
    listoUsarSinCartas: "Calculá una carta para usarlo",
    derechosBreve: "{n} lecturas breves",
    derechosBreveUno: "1 lectura breve",
    derechosInforme: "{n} informes completos",
    derechosInformeUno: "1 informe completo",
    sinDerechos: "Todavía no tenés ninguna lectura ni informe disponible.",
    comprarInforme: "Comprar el informe completo",
    comprarNota: "También podés llevarte un pack de 3 o 5 y usarlos cuando quieras.",
    conectadoComo: "Estás dentro como {email}.",
    conectadoSinMail: "Estás dentro con tu cuenta.",
    comprasTitle: "Tus compras",
    comprasEmpty: "Todavía no compraste nada.",
    compraPendiente: "Procesando el pago…",
    verPrecios: "Ver precios",
    account: "Tu cuenta",
    signOut: "Salir",
    chartsTitle: "Tus cartas",
    chartsEmpty: "Todavía no calculaste ninguna.",
    chartsEmptyCta: "Calcular mi carta",
    unnamedChart: "Carta sin nombre",
    readIn: "Lectura en",
    settings: "Privacidad y términos",
    dangerTitle: "Borrar mis datos",
    deleteChartsTitle: "Borrar mis cartas",
    deleteChartsBody: "Se borran todas tus cartas e interpretaciones. Lo que tengas disponible para leer no se pierde.",
    deleteChartsConfirm: "Sí, borrar mis cartas",
    deleteAccountTitle: "Borrar mi cuenta",
    deleteAccountBody: "Se borra todo: cartas, interpretaciones, lecturas e informes disponibles, y la cuenta. No se puede deshacer.",
    deleteAccountConfirm: "Sí, borrar mi cuenta",
    confirmHint: "Esta acción no se puede deshacer.",
    cancel: "Cancelar",
    working: "Borrando…",
  },
};

const en: Dict = {
  meta: {
    title: "ASTRA — astrological charts",
    description:
      "Your natal chart, computed from real ephemeris and written in your language. Straight from your browser, nothing to install.",
  },
  nav: { example: "Sample chart", notes: "Notes", precios: "Pricing" },
  theme: { night: "Night", day: "Day", label: "Page light" },
  rail: {
    eyebrow: "Ephemeris — now",
    note: "Geocentric positions for the moment you opened this page. They update on their own.",
  },
  hero: {
    title: "This is the sky while you read this.",
    lede:
      "The wheel isn't an illustration: these are the real positions of this very moment, from the same ephemeris ASTRA uses for your natal chart.",
    ledeStrong: "Enter your birth date, time and place and you'll see yours.",
    cta: "See my birth chart",
    ctaSecondary: "See a sample chart",
    wheelAlt: "Wheel showing the planetary positions of this moment",
  },
  flow: {
    eyebrow: "From your birth to the text",
    title: "Three steps between your birth and the reading.",
    steps: [
      {
        label: "Your details",
        title: "Date, time and place",
        body:
          "Places come from a 234,000-entry gazetteer that carries each one's time zone, so your birth time lands where it should.",
      },
      {
        label: "The calculation",
        title: "Ephemeris, not estimates",
        body:
          "Planetary positions, houses and aspects come from the Swiss Ephemeris — the same engine professional astrologers use.",
      },
      {
        label: "The text",
        title: "Your chart, in your language",
        body:
          "The text is written over the chart already calculated, and you can read it in Spanish, English or Portuguese without starting over.",
      },
    ],
  },
  notes: {
    eyebrow: "Notes",
    title: "What each thing in your chart actually means.",
    lede: "Astrology explained without the mysticism: what each piece of the chart measures, and what it doesn't.",
    empty: "No notes published in English yet. They're on the way.",
    back: "All notes",
    publishedOn: "Published on",
  },
  privacy: {
    eyebrow: "Privacy",
    title: "Your birth details never leave your account.",
    points: [
      {
        strong: "They're used for one thing.",
        rest: "Your date, your time and your birthplace are there to calculate your chart. Nothing else.",
      },
      {
        strong: "We don't sell or publish anything of yours.",
        rest: "Not your charts, not your readings, not your email. No ads either.",
      },
      {
        strong: "Deleting means deleting.",
        rest: "You can remove one chart or your whole account right here, and no copy is kept.",
      },
    ],
    link: "Read the full policy →",
  },
  pricing: {
    eyebrow: "Pricing",
    title: "Your first three short readings are free.\nThe full report is a separate purchase.",
    price: "US$ 29",
    priceNote: "the full report for one chart: eight sections, about 6,000 words",
    terms: [
      { label: "Your first 3 short readings", value: "Free", free: true },
      { label: "Full report for one chart", value: "US$ 29" },
      { label: "The same report in another language", value: "No charge", free: true },
      { label: "Packs of 3 or 5 reports", value: "From US$ 25 each" },
      { label: "Expiry", value: "They don't expire" },
    ],
    note: "Prices in US dollars. You pay directly on the web; the final amount may include tax depending on your country.",
    cta: "See all pricing",
  },
  faq: {
    eyebrow: "Questions",
    title: "What everyone asks before they start.",
    items: [
      {
        q: "Do I need my exact birth time?",
        a: "It helps a lot: the Ascendant and the houses shift a degree every four minutes. You can build a chart without a time, but then it has no houses, no Ascendant, no aspects, and the Moon's position is approximate.",
      },
      {
        q: "What languages is it in?",
        a: "Spanish, English and Portuguese. Reading a chart you already generated in another language costs nothing.",
      },
      {
        q: "Is the calculation serious, or is this a horoscope?",
        a: "The calculation is serious: Swiss Ephemeris, Placidus houses, tropical zodiac — the same ones a professional astrologer uses. What you read is written over that calculation, and it's for entertainment and self-reflection.",
      },
      {
        q: "Do I need an account?",
        a: "You sign in with your Google account. No passwords to remember, no form to fill in.",
      },
      {
        q: "Can I make charts for other people?",
        a: "Yes. Every chart you save stays in your account under the name you give it, and you can delete it whenever you want.",
      },
      {
        q: "What happens if I delete my account?",
        a: "Your charts, readings and whatever you have available to read are erased, with no backup copy. It's permanent, and you do it yourself from your account.",
      },
    ],
  },
  cierre: {
    eyebrow: "Get started",
    title: "Start with yours.",
    note: "In your browser, nothing to install. Your first short reading costs nothing.",
    cta: "See my birth chart",
  },
  chart: {
    back: "← Your charts",
    noWheel: "This chart has no wheel.",
    noWheelBody: "It was entered without a birth time, so there's no Ascendant or houses to orient it. The planetary positions are there.",
    incomplete: "A body is missing: its ephemeris doesn't cover that date.",
    interpretBreve: "Read the short reading",
    interpretBreveNota: "Free. You have {n} left.",
    interpretCompleto: "Buy the full report",
    comoSeEscribe: "How your reading is written",
    interpretCompletoConDerecho: "Read the full report",
    compraFallo: "We couldn't open the payment. Try again in a moment.",
    interpretCompletoNota: "US$ 29 · eight sections",
    interpretCompletoNotaSinHora: "US$ 29 · seven sections",
    interpretCompletoNotaConDerecho: "Already paid for · eight sections",
    interpretCompletoNotaConDerechoSinHora: "Already paid for · seven sections",
    interpretCompletoSaldo: "You'll have {n} left after this one.",
    interpretFreeLang: "No cost: you already read it in another language.",
    interpreting: "Writing your reading…",
    readAgain: "See the reading",
    capDiario: "Today's free short readings are gone. Come back tomorrow, or read the full report.",
    demasiados: "Too many attempts in a row. Wait a moment and try again.",
    sinLeerBreve: "You're out of free short readings.",
    sinLeerInforme: "You haven't bought the full report yet.",
    sinDerecho: "You don't have this reading available.",
    failed: "We couldn't generate the reading. Try again in a while.",
    generationInProgress:
      "There's already a generation in progress for this chart in another language. Wait a few seconds and try again.",
    columns: { body: "Body", position: "Position", house: "House" },
    houses: "Houses",
    aspects: "Aspects",
    axisNames: { AC: "Ascendant", MC: "Midheaven" },
    aspectColumns: { pair: "Between", aspect: "Aspect", orb: "Orb" },
    show: "Show",
    hide: "Hide",
    waitTitle: "Reading your sky",
    waitBody: "We're writing your report, in eight sections. Each one is thought through on its own, with your whole chart in view — that's why it takes about six minutes.",
    waitBodyBreve: "We're writing your short reading. It takes half a minute.",
    waitProgress: "We're on section {hechas} of {total}.",
    waitColor: "You can close this window. There are no pre-written charts here: every section is written for this chart and no other, which is why it can take up to six minutes. When it's ready, it will be waiting in your account.",
    noTimeWarning: "This chart has no birth time: the report comes out with seven sections, without the houses one.",
    reading: "Your reading",
    resumenTitulo: "What the full report includes",
    resumenRestante: "+{n} words",
    resumenCta: "Buy the full report to read them all.",
  },
  compra: {
    title: "All set, thank you",
    body: "We're confirming your payment. It takes a few seconds, and then we'll take you straight to what you bought.",
    demoraTitle: "Your payment went through",
    demoraBody: "The confirmation is taking longer than usual. There's no need to pay again: as soon as it arrives, you'll find it in your account. If it doesn't show up in a few minutes, write to us at info@astraguia.com.",
    sinDatoTitle: "Thank you for your purchase",
    sinDatoBody: "What you bought is waiting in your account.",
    irACuenta: "Go to my account",
  },
  share: {
    chartEyebrow: "Natal chart",
    positionsTitle: "Positions",
    downloadsTitle: "Downloads",
    pdf: "Chart PDF",
    pdfWithReading: "Full PDF",
    pdfWithReadingIn: "Full PDF (in {lang})",
    image: "The chart as an image",
    pdfHint: "Wheel, positions and aspects",
    pdfWithReadingHint: "Everything in one file, ready to print",
    imageHint: "1080×1920, for stories",
    working: "Preparing…",
    failed: "We couldn't prepare the file. Try again.",
    tagline: "Your natal chart",
    madeWith: "Made with ASTRA",
    langNames: { es: "Spanish", en: "English", pt: "Portuguese" },
  },
  newChart: {
    navNew: "New chart",
    title: "Compute your chart.",
    lede: "With the date, time and place where you were born.",
    name: "Name",
    namePlaceholder: "To recognise it later",
    nameHint: "Optional. It isn't used to compute anything.",
    date: "Date of birth",
    time: "Time",
    timeUnknown: "I don't know the time",
    timeUnknownHint: "Without a time there's no Ascendant, no houses, no aspects, and the Moon is approximate.",
    place: "Place of birth",
    placePlaceholder: "City or town",
    searching: "Searching…",
    noPlaces: "We couldn't find that place. Try the nearest city.",
    changePlace: "Change",
    submit: "Compute my chart",
    submitting: "Computing…",
    needPlace: "Choose the place of birth.",
    needDate: "The date of birth is missing.",
    badDate: "Check the date: it has to be after 1800 and can't be in the future.",
    failed: "We couldn't compute the chart. Check the details and try again.",
    sinLeerBreve: "You've used up your free short readings.",
  },
  foot: { brand: "ASTRA · Astrological charts", privacy: "Privacy", terms: "Terms", contact: "Contact" },
  consent: {
    text: "It helps us to know how many people arrive and which pages they read. No ads, no data selling, and never your name or your birth details.",
    accept: "Accept",
    reject: "No thanks",
    more: "How we handle your data",
    footLink: "Analytics",
  },
  precios: {
    title: "Choose how you want to read yourself.",
    lede: "Buy once, use it whenever: the reports in a pack don't expire.",
    nombre: {
      informe_natal: "Full report",
      pack_3_natal: "Three reports",
      pack_5_natal: "Five reports",
    },
    detalle: {
      informe_natal: "Your birth chart interpreted in eight sections, around 6,000 words. Read it on the web and download the PDF.",
      pack_3_natal: "Three full reports to use on the charts you choose, whenever you want.",
      pack_5_natal: "Five full reports to use on the charts you choose, whenever you want.",
    },
    porUnidad: "{precio} each",
    comprar: "Buy",
    abriendo: "Opening checkout…",
    fallo: "We couldn't open the checkout. Please try again.",
    sinCatalogo: "We couldn't load pricing. Please try again in a moment.",
    gratisNombre: "Short reading",
    gratisPrecio: "Free",
    gratisDetalle: "Three per account, no card. Your chart in a few paragraphs.",
    recomendado: "Most chosen",
    verEjemplo: "See an example",
    nota: "The reports you buy stay in your account until you use them. Payment is handled by Stripe; your country's tax is already included in the price.",
  },
  auth: {
    navEnter: "Sign in",
    title: "Sign in to your account.",
    lede: "Your charts and your readings stay saved in your account.",
    loading: "Loading…",
    blocked: "We couldn't load Google sign-in. This usually comes from a tracker blocker: allow this site and reload.",
    failed: "We couldn't sign you in. Try again.",
    legal: "By signing in you accept the terms and the privacy policy.",
    listoTitle: "Ready to use",
    listoUsar: "Pick a chart to use it on",
    listoUsarSinCartas: "Calculate a chart to use it on",
    derechosBreve: "{n} short readings",
    derechosBreveUno: "1 short reading",
    derechosInforme: "{n} full reports",
    derechosInformeUno: "1 full report",
    sinDerechos: "You don't have any reading or report available yet.",
    comprarInforme: "Buy the full report",
    comprarNota: "You can also get a pack of 3 or 5 and use them whenever you want.",
    conectadoComo: "You're signed in as {email}.",
    conectadoSinMail: "You're signed in.",
    comprasTitle: "Your purchases",
    comprasEmpty: "You haven't bought anything yet.",
    compraPendiente: "Processing payment…",
    verPrecios: "See pricing",
    account: "Your account",
    signOut: "Sign out",
    chartsTitle: "Your charts",
    chartsEmpty: "You haven't computed any yet.",
    chartsEmptyCta: "Compute my chart",
    unnamedChart: "Unnamed chart",
    readIn: "Reading in",
    settings: "Privacy and terms",
    dangerTitle: "Delete my data",
    deleteChartsTitle: "Delete my charts",
    deleteChartsBody: "All your charts and readings are deleted. What you have available to read isn't lost.",
    deleteChartsConfirm: "Yes, delete my charts",
    deleteAccountTitle: "Delete my account",
    deleteAccountBody: "Everything goes: charts, readings, whatever you have available to read, and the account. It can't be undone.",
    deleteAccountConfirm: "Yes, delete my account",
    confirmHint: "This action can't be undone.",
    cancel: "Cancel",
    working: "Deleting…",
  },
};

const pt: Dict = {
  meta: {
    title: "ASTRA — mapas astrais",
    description:
      "Seu mapa natal calculado com efemérides reais e escrito no seu idioma. Direto no navegador, sem instalar nada.",
  },
  nav: { example: "Mapa de exemplo", notes: "Notas", precios: "Preços" },
  theme: { night: "Noite", day: "Dia", label: "Luz da página" },
  rail: {
    eyebrow: "Efeméride — agora",
    note: "Posições geocêntricas do momento em que você abriu a página. Elas se atualizam sozinhas.",
  },
  hero: {
    title: "É assim que está o céu enquanto você lê isto.",
    lede:
      "A roda não é uma ilustração: são as posições reais deste instante, calculadas com as mesmas efemérides que o ASTRA usa no seu mapa natal.",
    ledeStrong: "Informe sua data, hora e local de nascimento e você vai ver o seu.",
    cta: "Ver meu mapa natal",
    ctaSecondary: "Ver um mapa de exemplo",
    wheelAlt: "Roda com as posições planetárias deste momento",
  },
  flow: {
    eyebrow: "Do nascimento ao texto",
    title: "Três passos entre o seu nascimento e a leitura.",
    steps: [
      {
        label: "Seus dados",
        title: "Data, hora e lugar",
        body:
          "O lugar é buscado num cadastro de 234.000 localidades que traz o fuso horário de cada uma, para que a hora de nascimento caia onde deve.",
      },
      {
        label: "O cálculo",
        title: "Efemérides, não aproximações",
        body:
          "Posições planetárias, casas e aspectos saem do Swiss Ephemeris — o mesmo motor que os astrólogos profissionais usam.",
      },
      {
        label: "O texto",
        title: "Seu mapa, no seu idioma",
        body:
          "O texto é escrito sobre o mapa já calculado, e você pode lê-lo em espanhol, inglês ou português sem recomeçar.",
      },
    ],
  },
  notes: {
    eyebrow: "Notas",
    title: "O que significa cada coisa que você vê no seu mapa.",
    lede: "Astrologia explicada sem misticismo: o que cada peça do mapa mede e o que não mede.",
    empty: "Ainda não há notas publicadas em português. Estão a caminho.",
    back: "Todas as notas",
    publishedOn: "Publicada em",
  },
  privacy: {
    eyebrow: "Privacidade",
    title: "Seus dados de nascimento não saem da sua conta.",
    points: [
      {
        strong: "Servem para uma coisa só.",
        rest: "Sua data, sua hora e o lugar onde você nasceu servem para calcular o seu mapa. Nada além disso.",
      },
      {
        strong: "Não vendemos nem publicamos nada seu.",
        rest: "Nem seus mapas, nem suas leituras, nem seu email. Também não mostramos publicidade.",
      },
      {
        strong: "Apagar é apagar.",
        rest: "Você pode excluir um mapa ou a conta inteira aqui mesmo, e não fica cópia.",
      },
    ],
    link: "Ler a política completa →",
  },
  pricing: {
    eyebrow: "Preços",
    title: "Suas primeiras três leituras breves são grátis.\nO relatório completo é comprado à parte.",
    price: "US$ 29",
    priceNote: "o relatório completo de um mapa: oito seções, cerca de 6.000 palavras",
    terms: [
      { label: "Suas primeiras 3 leituras breves", value: "Grátis", free: true },
      { label: "Relatório completo de um mapa", value: "US$ 29" },
      { label: "O mesmo relatório em outro idioma", value: "Sem custo", free: true },
      { label: "Pacotes de 3 ou 5 relatórios", value: "A partir de US$ 25 cada" },
      { label: "Validade", value: "Não expiram" },
    ],
    note: "Preços em dólares. O pagamento é feito direto pela web; o valor final pode incluir impostos conforme o seu país.",
    cta: "Ver todos os preços",
  },
  faq: {
    eyebrow: "Perguntas",
    title: "O que todo mundo pergunta antes de começar.",
    items: [
      {
        q: "Preciso da hora exata de nascimento?",
        a: "Ajuda muito: o Ascendente e as casas se deslocam um grau a cada quatro minutos. Você pode montar o mapa sem hora, mas aí ele não tem casas, nem Ascendente, nem aspectos, e a posição da Lua fica aproximada.",
      },
      {
        q: "Em quais idiomas está?",
        a: "Espanhol, inglês e português. Ler um mapa que você já gerou em outro idioma não custa nada.",
      },
      {
        q: "O cálculo é sério ou é horóscopo?",
        a: "O cálculo é sério: Swiss Ephemeris, casas Placidus, zodíaco tropical — os mesmos que um astrólogo profissional usa. O que você lê é escrito sobre esse cálculo, e é para entretenimento e autoconhecimento.",
      },
      {
        q: "Preciso criar uma conta?",
        a: "Você entra com sua conta do Google. Sem senha para lembrar e sem formulário para preencher.",
      },
      {
        q: "Posso fazer mapas de outras pessoas?",
        a: "Pode. Cada mapa que você salva fica na sua conta com o nome que você der, e dá para apagar quando quiser.",
      },
      {
        q: "O que acontece se eu apagar minha conta?",
        a: "Seus mapas, leituras e o que você tiver disponível para ler são apagados, sem cópia de segurança. É definitivo e você mesmo faz pela sua conta.",
      },
    ],
  },
  cierre: {
    eyebrow: "Começar",
    title: "Comece pelo seu.",
    note: "No navegador, sem instalar nada. Sua primeira leitura breve não custa nada.",
    cta: "Ver meu mapa natal",
  },
  chart: {
    back: "← Seus mapas",
    noWheel: "Este mapa não tem roda.",
    noWheelBody: "Foi criado sem hora de nascimento, então não há Ascendente nem casas para orientá-la. As posições planetárias estão.",
    incomplete: "Falta algum corpo: a efeméride dele não cobre essa data.",
    interpretBreve: "Ler a leitura breve",
    interpretBreveNota: "Grátis. Restam {n}.",
    interpretCompleto: "Comprar o relatório completo",
    comoSeEscribe: "Como sua leitura é escrita",
    interpretCompletoConDerecho: "Ler o relatório completo",
    compraFallo: "Não conseguimos abrir o pagamento. Tente de novo em instantes.",
    interpretCompletoNota: "US$ 29 · oito seções",
    interpretCompletoNotaSinHora: "US$ 29 · sete seções",
    interpretCompletoNotaConDerecho: "Já está pago · oito seções",
    interpretCompletoNotaConDerechoSinHora: "Já está pago · sete seções",
    interpretCompletoSaldo: "Depois deste ainda ficam {n}.",
    interpretFreeLang: "Sem custo: você já leu em outro idioma.",
    interpreting: "Escrevendo sua leitura…",
    readAgain: "Ver a leitura",
    capDiario: "As leituras breves grátis de hoje acabaram. Volte amanhã, ou leia o relatório completo.",
    demasiados: "Tentativas demais seguidas. Espere um momento e tente de novo.",
    sinLeerBreve: "Você ficou sem leituras breves grátis.",
    sinLeerInforme: "Você ainda não comprou o relatório completo.",
    sinDerecho: "Você não tem essa leitura disponível.",
    failed: "Não conseguimos gerar a leitura. Tente de novo daqui a pouco.",
    generationInProgress:
      "Já há uma geração em andamento para este mapa em outro idioma. Espere alguns segundos e tente de novo.",
    columns: { body: "Corpo", position: "Posição", house: "Casa" },
    houses: "Casas",
    aspects: "Aspectos",
    axisNames: { AC: "Ascendente", MC: "Meio do Céu" },
    aspectColumns: { pair: "Entre", aspect: "Aspecto", orb: "Orbe" },
    show: "Ver",
    hide: "Ocultar",
    waitTitle: "Lendo o seu céu",
    waitBody: "Estamos escrevendo seu relatório, em oito seções. Cada uma é pensada em separado, com o seu mapa inteiro à frente: por isso leva uns seis minutos.",
    waitBodyBreve: "Estamos escrevendo sua leitura breve. Leva meio minuto.",
    waitProgress: "Vamos na seção {hechas} de {total}.",
    waitColor: "Você pode fechar esta janela. Aqui não há mapas prontos: cada seção é escrita para este mapa e só para ele, e por isso pode levar até seis minutos. Quando estiver pronto, espera na sua conta.",
    noTimeWarning: "Este mapa ficou sem hora de nascimento: o relatório sai com sete seções, sem a de casas.",
    reading: "Sua leitura",
    resumenTitulo: "O que o relatório completo traz",
    resumenRestante: "+{n} palavras",
    resumenCta: "Compre o relatório completo para ler tudo.",
  },
  compra: {
    title: "Pronto, obrigado",
    body: "Estamos confirmando seu pagamento. Leva alguns segundos e levamos você direto ao que comprou.",
    demoraTitle: "Seu pagamento foi feito",
    demoraBody: "A confirmação está demorando mais que o normal. Não precisa pagar de novo: assim que chegar, você vai encontrar na sua conta. Se em alguns minutos não aparecer, escreva para info@astraguia.com.",
    sinDatoTitle: "Obrigado pela sua compra",
    sinDatoBody: "O que você comprou espera na sua conta.",
    irACuenta: "Ir para minha conta",
  },
  share: {
    chartEyebrow: "Mapa natal",
    positionsTitle: "Posições",
    downloadsTitle: "Downloads",
    pdf: "PDF do mapa",
    pdfWithReading: "PDF completo",
    pdfWithReadingIn: "PDF completo (em {lang})",
    image: "O mapa como imagem",
    pdfHint: "Roda, posições e aspectos",
    pdfWithReadingHint: "O mapa e sua leitura, pronto para imprimir",
    imageHint: "1080×1920, para stories",
    working: "Preparando…",
    failed: "Não conseguimos preparar o arquivo. Tente de novo.",
    tagline: "Seu mapa natal",
    madeWith: "Feito com ASTRA",
    langNames: { es: "espanhol", en: "inglês", pt: "português" },
  },
  newChart: {
    navNew: "Novo mapa",
    title: "Calcule seu mapa.",
    lede: "Com a data, a hora e o lugar onde você nasceu.",
    name: "Nome",
    namePlaceholder: "Para reconhecê-lo depois",
    nameHint: "Opcional. Não é usado para calcular nada.",
    date: "Data de nascimento",
    time: "Hora",
    timeUnknown: "Não sei a hora",
    timeUnknownHint: "Sem hora não há Ascendente, nem casas, nem aspectos, e a Lua fica aproximada.",
    place: "Local de nascimento",
    placePlaceholder: "Cidade ou município",
    searching: "Buscando…",
    noPlaces: "Não encontramos esse lugar. Tente a cidade mais próxima.",
    changePlace: "Trocar",
    submit: "Calcular meu mapa",
    submitting: "Calculando…",
    needPlace: "Escolha o local de nascimento.",
    needDate: "Falta a data de nascimento.",
    badDate: "Revise a data: precisa ser posterior a 1800 e não pode estar no futuro.",
    failed: "Não conseguimos calcular o mapa. Revise os dados e tente de novo.",
    sinLeerBreve: "Você já usou suas leituras breves grátis.",
  },
  foot: { brand: "ASTRA · Mapas astrais", privacy: "Privacidade", terms: "Termos", contact: "Contato" },
  consent: {
    text: "Ajuda-nos saber quantas pessoas chegam e quais páginas leem. Sem publicidade, sem vender dados e sem o seu nome nem os seus dados de nascimento.",
    accept: "Aceitar",
    reject: "Não, obrigado",
    more: "Como tratamos os seus dados",
    footLink: "Analítica",
  },
  precios: {
    title: "Escolha como quer se ler.",
    lede: "Compre uma vez e use quando quiser: os relatórios de um pacote não expiram.",
    nombre: {
      informe_natal: "Relatório completo",
      pack_3_natal: "Três relatórios",
      pack_5_natal: "Cinco relatórios",
    },
    detalle: {
      informe_natal: "Seu mapa natal interpretado em oito seções, cerca de 6.000 palavras. Leia na web e baixe o PDF.",
      pack_3_natal: "Três relatórios completos para usar nos mapas que você escolher, quando quiser.",
      pack_5_natal: "Cinco relatórios completos para usar nos mapas que você escolher, quando quiser.",
    },
    porUnidad: "{precio} cada um",
    comprar: "Comprar",
    abriendo: "Abrindo o pagamento…",
    fallo: "Não conseguimos abrir o pagamento. Tente de novo.",
    sinCatalogo: "Não conseguimos carregar os preços. Tente de novo em instantes.",
    gratisNombre: "Leitura breve",
    gratisPrecio: "Grátis",
    gratisDetalle: "Três por conta, sem cartão. Seu mapa em alguns parágrafos.",
    recomendado: "O mais escolhido",
    verEjemplo: "Ver um exemplo",
    nota: "Os relatórios que você comprar ficam na sua conta até serem usados. O pagamento é processado pela Stripe; o imposto do seu país já está incluído no preço.",
  },
  auth: {
    navEnter: "Entrar",
    title: "Entre na sua conta.",
    lede: "Seus mapas e suas leituras ficam salvos na sua conta.",
    loading: "Carregando…",
    blocked: "Não conseguimos carregar o acesso do Google. Costuma ser um bloqueador de rastreadores: libere este site e recarregue.",
    failed: "Não conseguimos entrar. Tente de novo.",
    legal: "Ao entrar você aceita os termos e a política de privacidade.",
    listoTitle: "Pronto para usar",
    listoUsar: "Escolha um mapa para usar",
    listoUsarSinCartas: "Calcule um mapa para usar",
    derechosBreve: "{n} leituras breves",
    derechosBreveUno: "1 leitura breve",
    derechosInforme: "{n} relatórios completos",
    derechosInformeUno: "1 relatório completo",
    sinDerechos: "Você ainda não tem nenhuma leitura nem relatório disponível.",
    comprarInforme: "Comprar o relatório completo",
    comprarNota: "Você também pode levar um pacote de 3 ou 5 e usá-los quando quiser.",
    conectadoComo: "Você entrou como {email}.",
    conectadoSinMail: "Você entrou na sua conta.",
    comprasTitle: "Suas compras",
    comprasEmpty: "Você ainda não comprou nada.",
    compraPendiente: "Processando o pagamento…",
    verPrecios: "Ver preços",
    account: "Sua conta",
    signOut: "Sair",
    chartsTitle: "Seus mapas",
    chartsEmpty: "Você ainda não calculou nenhum.",
    chartsEmptyCta: "Calcular meu mapa",
    unnamedChart: "Mapa sem nome",
    readIn: "Leitura em",
    settings: "Privacidade e termos",
    dangerTitle: "Apagar meus dados",
    deleteChartsTitle: "Apagar meus mapas",
    deleteChartsBody: "Todos os seus mapas e leituras são apagados. O que você tiver disponível para ler não se perde.",
    deleteChartsConfirm: "Sim, apagar meus mapas",
    deleteAccountTitle: "Apagar minha conta",
    deleteAccountBody: "Apaga tudo: mapas, leituras, o que você tiver disponível para ler, e a conta. Não dá para desfazer.",
    deleteAccountConfirm: "Sim, apagar minha conta",
    confirmHint: "Esta ação não pode ser desfeita.",
    cancel: "Cancelar",
    working: "Apagando…",
  },
};

export const DICTS: Record<Locale, Dict> = { es, en, pt };

export function getDict(locale: Locale): Dict {
  return DICTS[locale];
}
