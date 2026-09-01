// Diccionarios de la web. Sin librería: son tres idiomas y un puñado de claves,
// y next-intl traería un middleware y un provider para resolver un objeto.

export const LOCALES = ["es", "en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
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
  nav: { example: string; notes: string; download: string };
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
  credits: {
    eyebrow: string;
    title: string;
    /** El único precio decidido hoy: el informe completo, comprado suelto. */
    price: string;
    priceNote: string;
    terms: { label: string; value: string; free?: boolean }[];
    note: string;
  };
  faq: { eyebrow: string; title: string; items: { q: string; a: string }[] };
  download: {
    eyebrow: string;
    title: string;
    note: string;
    appleSmall: string;
    playSmall: string;
    /** Las apps se anuncian pero todavía no están publicadas. */
    soon: string;
  };
  foot: { brand: string; privacy: string; terms: string; contact: string };
  consent: { text: string; accept: string; reject: string; more: string; footLink: string };
  auth: {
    navEnter: string;
    title: string;
    lede: string;
    loading: string;
    blocked: string;
    failed: string;
    legal: string;
    /** Saldo de lecturas breves gratis (arranca en 3, no se compran). */
    freeCredits: string;
    /** Saldo de créditos pagos: cada uno compra un informe completo. */
    paidCredits: string;
    account: string;
    signOut: string;
    buyCredits: string;
    buyInApp: string;
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
    /** Nota bajo el botón de la breve. Lleva `{n}`: cuántos créditos gratis quedan. */
    interpretBreveNota: string;
    /** Botón del informe completo pago (tier "largo"). */
    interpretCompleto: string;
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
     * Nota de cualquiera de los dos botones cuando ESE tier ya está completo
     * en otro idioma: traducirlo no cuesta (el backend lo resuelve sin tocar
     * el ledger), así que reemplaza a `interpretBreveNota`/
     * `interpretCompletoNota` — decir el precio ahí sería mentir.
     */
    interpretFreeLang: string;
    interpreting: string;
    readAgain: string;
    noCredits: string;
    /** 402 con code "sin_leer_breve": se acabó el lote de lecturas breves gratis. */
    sinFree: string;
    /** 402 con code "sin_leer_informe": el informe completo todavía no está comprado. */
    sinPaid: string;
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
    /** RF12: aviso previo, antes de gastar el crédito, si la carta no tiene hora. */
    noTimeWarning: string;
    reading: string;
    /** Encabezado del pie que muestra qué trae el informe completo (Task 15). */
    resumenTitulo: string;
    /** Cuánto falta de cada sección todavía sin comprar. Lleva `{n}`: palabras. */
    resumenRestante: string;
    /** Cierre del pie, invitando a comprar el informe completo. */
    resumenCta: string;
  };
  share: {
    /** Rótulo de la portada del documento y título de la tabla de posiciones. */
    chartEyebrow: string;
    positionsTitle: string;
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
    noCredits: string;
  };
};

const es: Dict = {
  meta: {
    title: "ASTRA — cartas astrales",
    description:
      "Tu carta natal calculada con efemérides reales y leída en tu idioma. Directo en el navegador, sin instalar nada.",
  },
  nav: { example: "Carta de ejemplo", notes: "Notas", download: "Descargar" },
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
    cta: "Descargar ASTRA",
    ctaSecondary: "Ver una carta de ejemplo",
    wheelAlt: "Rueda con las posiciones planetarias del momento actual",
  },
  flow: {
    eyebrow: "De tu fecha al texto",
    title: "Tres pasos entre tu nacimiento y la lectura.",
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
        label: "La lectura",
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
        rest: "Podés eliminar una carta o toda tu cuenta desde la app, y no queda copia.",
      },
    ],
    link: "Leer la política completa →",
  },
  credits: {
    eyebrow: "Créditos",
    title: "Tus primeras tres lecturas son gratis.\nEl informe completo se compra aparte.",
    price: "US$ 29",
    priceNote: "el informe completo de una carta: ocho secciones, unas 6.000 palabras",
    terms: [
      { label: "Tus primeras 3 lecturas breves", value: "Gratis", free: true },
      { label: "Informe completo de una carta", value: "US$ 29" },
      { label: "El mismo informe en otro idioma", value: "Sin costo", free: true },
      { label: "Vencimiento", value: "No vencen" },
    ],
    note: "Precios en dólares. Se paga directo en la web; el importe final puede incluir impuestos según tu país.",
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
        a: "Español, inglés y portugués. Leer una carta que ya generaste en otro idioma no consume créditos.",
      },
      {
        q: "¿El cálculo es serio o es un horóscopo?",
        a: "El cálculo es serio: Swiss Ephemeris, casas Placidus, zodíaco tropical, los mismos que usa un astrólogo profesional. Lo que leés se escribe sobre ese cálculo, y es para entretenimiento y autoconocimiento.",
      },
      {
        q: "¿Necesito crear una cuenta?",
        a: "Entrás con Apple o Google. No hay contraseñas que recordar ni formulario que completar.",
      },
      {
        q: "¿Puedo hacer cartas de otras personas?",
        a: "Sí. Cada carta que guardás queda en tu cuenta con el nombre que le pongas, y podés borrarla cuando quieras.",
      },
      {
        q: "¿Qué pasa si borro mi cuenta?",
        a: "Se eliminan tus cartas, tus lecturas y tus créditos, sin copia de respaldo. Es definitivo y lo hacés vos desde la app.",
      },
    ],
  },
  download: {
    eyebrow: "Descargar",
    title: "Empezá por la tuya.",
    note: "Android e iOS. La primera carta no cuesta nada.",
    appleSmall: "Descargar en el",
    playSmall: "Disponible en",
    soon: "Próximamente",
  },
  chart: {
    back: "← Tus cartas",
    noWheel: "Esta carta no tiene rueda.",
    noWheelBody: "Se cargó sin hora de nacimiento, así que no hay Ascendente ni casas para orientarla. Las posiciones planetarias sí están.",
    incomplete: "Falta algún cuerpo: su efeméride no cubre esa fecha.",
    interpretBreve: "Leer la lectura breve",
    interpretBreveNota: "Gratis. Te quedan {n}.",
    interpretCompleto: "Comprar el informe completo",
    interpretCompletoNota: "US$ 29 · ocho secciones",
    interpretCompletoNotaSinHora: "US$ 29 · siete secciones",
    interpretFreeLang: "Sin costo: ya lo leíste en otro idioma.",
    interpreting: "Escribiendo tu lectura…",
    readAgain: "Ver la lectura",
    noCredits: "Te quedaste sin créditos.",
    sinFree: "Te quedaste sin lecturas breves gratis.",
    sinPaid: "Todavía no compraste el informe completo.",
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
    waitBody: "Estamos escribiendo tu informe, en ocho secciones. Tarda unos minutos: no hace falta que te quedes en esta pantalla.",
    waitBodyBreve: "Estamos escribiendo tu lectura breve. Tarda un momento: no hace falta que te quedes en esta pantalla.",
    waitProgress: "Vamos por la sección {hechas} de {total}.",
    noTimeWarning: "Esta carta quedó sin hora de nacimiento: el informe sale con siete secciones, sin la de casas.",
    reading: "Tu lectura",
    resumenTitulo: "Esto trae el informe completo",
    resumenRestante: "+{n} palabras",
    resumenCta: "Comprá el informe completo para leerlas todas.",
  },
  share: {
    chartEyebrow: "Carta natal",
    positionsTitle: "Posiciones",
    pdf: "La carta en PDF",
    pdfWithReading: "La carta y tu lectura",
    pdfWithReadingIn: "La carta y tu lectura (en {lang})",
    image: "Imagen para redes",
    pdfHint: "Rueda, posiciones y aspectos",
    pdfWithReadingHint: "Todo en un archivo, listo para imprimir",
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
    noCredits: "Te quedaste sin créditos.",
  },
  foot: { brand: "ASTRA · Cartas astrales", privacy: "Privacidad", terms: "Términos", contact: "Contacto" },
  consent: {
    text: "Nos ayuda saber cuánta gente entra y qué páginas mira. Sin publicidad, sin vender datos y sin tu nombre ni tus datos de nacimiento.",
    accept: "Aceptar",
    reject: "No, gracias",
    more: "Cómo tratamos tus datos",
    footLink: "Analítica",
  },
  auth: {
    navEnter: "Entrar",
    title: "Entrá a tu cuenta.",
    lede: "La misma cuenta que en la app: tus cartas y tus créditos son los mismos.",
    loading: "Cargando…",
    blocked: "No pudimos cargar el acceso de Google. Suele pasar con bloqueadores de rastreadores: desactivalo para este sitio y recargá.",
    failed: "No pudimos iniciar sesión. Probá de nuevo.",
    legal: "Al entrar aceptás los términos y la política de privacidad.",
    freeCredits: "lecturas breves gratis",
    paidCredits: "créditos para informes",
    account: "Tu cuenta",
    signOut: "Salir",
    buyCredits: "Sumar créditos",
    buyInApp: "Por ahora no podés comprar créditos: el cobro en la web todavía no está activo.",
    chartsTitle: "Tus cartas",
    chartsEmpty: "Todavía no calculaste ninguna.",
    chartsEmptyCta: "Calcular mi carta",
    unnamedChart: "Carta sin nombre",
    readIn: "Lectura en",
    settings: "Privacidad y términos",
    dangerTitle: "Borrar mis datos",
    deleteChartsTitle: "Borrar mis cartas",
    deleteChartsBody: "Se borran todas tus cartas e interpretaciones. Tu cuenta y tus créditos quedan.",
    deleteChartsConfirm: "Sí, borrar mis cartas",
    deleteAccountTitle: "Borrar mi cuenta",
    deleteAccountBody: "Se borra todo: cartas, interpretaciones, créditos y la cuenta. No se puede deshacer.",
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
  nav: { example: "Sample chart", notes: "Notes", download: "Download" },
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
    cta: "Download ASTRA",
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
        label: "The reading",
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
        rest: "You can remove one chart or your whole account from the app, and no copy is kept.",
      },
    ],
    link: "Read the full policy →",
  },
  credits: {
    eyebrow: "Credits",
    title: "Your first three readings are free.\nThe full report is a separate purchase.",
    price: "US$ 29",
    priceNote: "the full report for one chart: eight sections, about 6,000 words",
    terms: [
      { label: "Your first 3 short readings", value: "Free", free: true },
      { label: "Full report for one chart", value: "US$ 29" },
      { label: "The same report in another language", value: "No charge", free: true },
      { label: "Expiry", value: "They don't expire" },
    ],
    note: "Prices in US dollars. You pay directly on the web; the final amount may include tax depending on your country.",
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
        a: "Spanish, English and Portuguese. Reading a chart you already generated in another language costs no credits.",
      },
      {
        q: "Is the calculation serious, or is this a horoscope?",
        a: "The calculation is serious: Swiss Ephemeris, Placidus houses, tropical zodiac — the same ones a professional astrologer uses. What you read is written over that calculation, and it's for entertainment and self-reflection.",
      },
      {
        q: "Do I need an account?",
        a: "You sign in with Apple or Google. No passwords to remember, no form to fill in.",
      },
      {
        q: "Can I make charts for other people?",
        a: "Yes. Every chart you save stays in your account under the name you give it, and you can delete it whenever you want.",
      },
      {
        q: "What happens if I delete my account?",
        a: "Your charts, readings and credits are erased, with no backup copy. It's permanent, and you do it yourself from the app.",
      },
    ],
  },
  download: {
    eyebrow: "Download",
    title: "Start with yours.",
    note: "Android and iOS. The first chart costs nothing.",
    appleSmall: "Download on the",
    playSmall: "Get it on",
    soon: "Coming soon",
  },
  chart: {
    back: "← Your charts",
    noWheel: "This chart has no wheel.",
    noWheelBody: "It was entered without a birth time, so there's no Ascendant or houses to orient it. The planetary positions are there.",
    incomplete: "A body is missing: its ephemeris doesn't cover that date.",
    interpretBreve: "Read the short reading",
    interpretBreveNota: "Free. You have {n} left.",
    interpretCompleto: "Buy the full report",
    interpretCompletoNota: "US$ 29 · eight sections",
    interpretCompletoNotaSinHora: "US$ 29 · seven sections",
    interpretFreeLang: "No cost: you already read it in another language.",
    interpreting: "Writing your reading…",
    readAgain: "See the reading",
    noCredits: "You've run out of credits.",
    sinFree: "You're out of free short readings.",
    sinPaid: "You haven't bought the full report yet.",
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
    waitBody: "We're writing your report, in eight sections. It takes a few minutes: no need to stay on this screen.",
    waitBodyBreve: "We're writing your short reading. It takes a moment: no need to stay on this screen.",
    waitProgress: "We're on section {hechas} of {total}.",
    noTimeWarning: "This chart has no birth time: the report comes out with seven sections, without the houses one.",
    reading: "Your reading",
    resumenTitulo: "What the full report includes",
    resumenRestante: "+{n} words",
    resumenCta: "Buy the full report to read them all.",
  },
  share: {
    chartEyebrow: "Natal chart",
    positionsTitle: "Positions",
    pdf: "The chart as PDF",
    pdfWithReading: "The chart and your reading",
    pdfWithReadingIn: "The chart and your reading (in {lang})",
    image: "Image for social",
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
    noCredits: "You've run out of credits.",
  },
  foot: { brand: "ASTRA · Astrological charts", privacy: "Privacy", terms: "Terms", contact: "Contact" },
  consent: {
    text: "It helps us to know how many people arrive and which pages they read. No ads, no data selling, and never your name or your birth details.",
    accept: "Accept",
    reject: "No thanks",
    more: "How we handle your data",
    footLink: "Analytics",
  },
  auth: {
    navEnter: "Sign in",
    title: "Sign in to your account.",
    lede: "The same account as in the app: your charts and your credits are the same.",
    loading: "Loading…",
    blocked: "We couldn't load Google sign-in. This usually comes from a tracker blocker: allow this site and reload.",
    failed: "We couldn't sign you in. Try again.",
    legal: "By signing in you accept the terms and the privacy policy.",
    freeCredits: "free short readings",
    paidCredits: "report credits",
    account: "Your account",
    signOut: "Sign out",
    buyCredits: "Add credits",
    buyInApp: "You can't buy credits yet: web checkout isn't live.",
    chartsTitle: "Your charts",
    chartsEmpty: "You haven't computed any yet.",
    chartsEmptyCta: "Compute my chart",
    unnamedChart: "Unnamed chart",
    readIn: "Reading in",
    settings: "Privacy and terms",
    dangerTitle: "Delete my data",
    deleteChartsTitle: "Delete my charts",
    deleteChartsBody: "All your charts and readings are deleted. Your account and your credits stay.",
    deleteChartsConfirm: "Yes, delete my charts",
    deleteAccountTitle: "Delete my account",
    deleteAccountBody: "Everything goes: charts, readings, credits and the account. It can't be undone.",
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
  nav: { example: "Mapa de exemplo", notes: "Notas", download: "Baixar" },
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
    cta: "Baixar o ASTRA",
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
        label: "A leitura",
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
        rest: "Você pode excluir um mapa ou a conta inteira pelo app, e não fica cópia.",
      },
    ],
    link: "Ler a política completa →",
  },
  credits: {
    eyebrow: "Créditos",
    title: "Suas primeiras três leituras são grátis.\nO relatório completo é comprado à parte.",
    price: "US$ 29",
    priceNote: "o relatório completo de um mapa: oito seções, cerca de 6.000 palavras",
    terms: [
      { label: "Suas primeiras 3 leituras breves", value: "Grátis", free: true },
      { label: "Relatório completo de um mapa", value: "US$ 29" },
      { label: "O mesmo relatório em outro idioma", value: "Sem custo", free: true },
      { label: "Validade", value: "Não expiram" },
    ],
    note: "Preços em dólares. O pagamento é feito direto pela web; o valor final pode incluir impostos conforme o seu país.",
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
        a: "Espanhol, inglês e português. Ler um mapa que você já gerou em outro idioma não consome créditos.",
      },
      {
        q: "O cálculo é sério ou é horóscopo?",
        a: "O cálculo é sério: Swiss Ephemeris, casas Placidus, zodíaco tropical — os mesmos que um astrólogo profissional usa. O que você lê é escrito sobre esse cálculo, e é para entretenimento e autoconhecimento.",
      },
      {
        q: "Preciso criar uma conta?",
        a: "Você entra com Apple ou Google. Sem senha para lembrar e sem formulário para preencher.",
      },
      {
        q: "Posso fazer mapas de outras pessoas?",
        a: "Pode. Cada mapa que você salva fica na sua conta com o nome que você der, e dá para apagar quando quiser.",
      },
      {
        q: "O que acontece se eu apagar minha conta?",
        a: "Seus mapas, leituras e créditos são apagados, sem cópia de segurança. É definitivo e você mesmo faz pelo app.",
      },
    ],
  },
  download: {
    eyebrow: "Baixar",
    title: "Comece pelo seu.",
    note: "Android e iOS. O primeiro mapa não custa nada.",
    appleSmall: "Baixar na",
    playSmall: "Disponível no",
    soon: "Em breve",
  },
  chart: {
    back: "← Seus mapas",
    noWheel: "Este mapa não tem roda.",
    noWheelBody: "Foi criado sem hora de nascimento, então não há Ascendente nem casas para orientá-la. As posições planetárias estão.",
    incomplete: "Falta algum corpo: a efeméride dele não cobre essa data.",
    interpretBreve: "Ler a leitura breve",
    interpretBreveNota: "Grátis. Restam {n}.",
    interpretCompleto: "Comprar o relatório completo",
    interpretCompletoNota: "US$ 29 · oito seções",
    interpretCompletoNotaSinHora: "US$ 29 · sete seções",
    interpretFreeLang: "Sem custo: você já leu em outro idioma.",
    interpreting: "Escrevendo sua leitura…",
    readAgain: "Ver a leitura",
    noCredits: "Você ficou sem créditos.",
    sinFree: "Você ficou sem leituras breves grátis.",
    sinPaid: "Você ainda não comprou o relatório completo.",
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
    waitBody: "Estamos escrevendo seu relatório, em oito seções. Leva alguns minutos: não precisa ficar nesta tela.",
    waitBodyBreve: "Estamos escrevendo sua leitura breve. Leva um instante: não precisa ficar nesta tela.",
    waitProgress: "Vamos na seção {hechas} de {total}.",
    noTimeWarning: "Este mapa ficou sem hora de nascimento: o relatório sai com sete seções, sem a de casas.",
    reading: "Sua leitura",
    resumenTitulo: "O que o relatório completo traz",
    resumenRestante: "+{n} palavras",
    resumenCta: "Compre o relatório completo para ler tudo.",
  },
  share: {
    chartEyebrow: "Mapa natal",
    positionsTitle: "Posições",
    pdf: "O mapa em PDF",
    pdfWithReading: "O mapa e sua leitura",
    pdfWithReadingIn: "O mapa e sua leitura (em {lang})",
    image: "Imagem para redes",
    pdfHint: "Roda, posições e aspectos",
    pdfWithReadingHint: "Tudo num arquivo, pronto para imprimir",
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
    noCredits: "Você ficou sem créditos.",
  },
  foot: { brand: "ASTRA · Mapas astrais", privacy: "Privacidade", terms: "Termos", contact: "Contato" },
  consent: {
    text: "Ajuda-nos saber quantas pessoas chegam e quais páginas leem. Sem publicidade, sem vender dados e sem o seu nome nem os seus dados de nascimento.",
    accept: "Aceitar",
    reject: "Não, obrigado",
    more: "Como tratamos os seus dados",
    footLink: "Analítica",
  },
  auth: {
    navEnter: "Entrar",
    title: "Entre na sua conta.",
    lede: "A mesma conta do app: seus mapas e seus créditos são os mesmos.",
    loading: "Carregando…",
    blocked: "Não conseguimos carregar o acesso do Google. Costuma ser um bloqueador de rastreadores: libere este site e recarregue.",
    failed: "Não conseguimos entrar. Tente de novo.",
    legal: "Ao entrar você aceita os termos e a política de privacidade.",
    freeCredits: "leituras breves grátis",
    paidCredits: "créditos para relatórios",
    account: "Sua conta",
    signOut: "Sair",
    buyCredits: "Adicionar créditos",
    buyInApp: "Por enquanto não é possível comprar créditos: o pagamento pela web ainda não está ativo.",
    chartsTitle: "Seus mapas",
    chartsEmpty: "Você ainda não calculou nenhum.",
    chartsEmptyCta: "Calcular meu mapa",
    unnamedChart: "Mapa sem nome",
    readIn: "Leitura em",
    settings: "Privacidade e termos",
    dangerTitle: "Apagar meus dados",
    deleteChartsTitle: "Apagar meus mapas",
    deleteChartsBody: "Todos os seus mapas e leituras são apagados. Sua conta e seus créditos ficam.",
    deleteChartsConfirm: "Sim, apagar meus mapas",
    deleteAccountTitle: "Apagar minha conta",
    deleteAccountBody: "Apaga tudo: mapas, leituras, créditos e a conta. Não dá para desfazer.",
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
