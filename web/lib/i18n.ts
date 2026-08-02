// Diccionarios de la web. Sin librería: son tres idiomas y un puñado de claves,
// y next-intl traería un middleware y un provider para resolver un objeto.

export const LOCALES = ["es", "en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
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
export const PLANET_NAME_BY_KEY: Record<Locale, Record<string, string>> = {
  es: Object.fromEntries(PLANET_NAMES.en.map((k, i) => [k, PLANET_NAMES.es[i]])),
  en: Object.fromEntries(PLANET_NAMES.en.map((k) => [k, k])),
  pt: Object.fromEntries(PLANET_NAMES.en.map((k, i) => [k, PLANET_NAMES.pt[i]])),
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
  notes: { eyebrow: string; title: string; items: { meta: string; title: string; sign: string }[] };
  privacy: { eyebrow: string; title: string; points: { strong: string; rest: string }[]; link: string };
  credits: {
    eyebrow: string;
    title: string;
    colCredits: string;
    colPrice: string;
    colUnit: string;
    popular: string;
    packs: { credits: string; price: string; unit: string; popular?: boolean }[];
    terms: { label: string; value: string; free?: boolean }[];
    note: string;
  };
  faq: { eyebrow: string; title: string; items: { q: string; a: string }[] };
  download: { eyebrow: string; title: string; note: string; appleSmall: string; playSmall: string };
  foot: { brand: string; privacy: string; terms: string; contact: string };
  auth: {
    navEnter: string;
    title: string;
    lede: string;
    loading: string;
    blocked: string;
    failed: string;
    legal: string;
    credits: string;
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
    interpret: string;
    interpretCost: string;
    interpreting: string;
    readAgain: string;
    noCredits: string;
    failed: string;
    columns: { body: string; position: string; house: string };
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
      "Tu carta natal calculada con efemérides reales y leída en tu idioma. Android e iOS.",
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
    items: [
      { meta: "28 jul 2026 · 7 min", title: "Por qué la hora exacta cambia toda tu carta", sign: "☊" },
      { meta: "14 jul 2026 · 5 min", title: "Sol, Luna y Ascendente: los tres que no son lo mismo", sign: "☉" },
      { meta: "2 jul 2026 · 9 min", title: "Mercurio retrógrado, explicado sin misticismo", sign: "☿" },
    ],
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
    title: "Tu primera carta es gratis. Después, un crédito por carta.",
    colCredits: "Créditos",
    colPrice: "Precio",
    colUnit: "Por carta",
    popular: "Más elegido",
    packs: [
      { credits: "3", price: "US$ 2,99", unit: "US$ 1,00" },
      { credits: "10", price: "US$ 6,99", unit: "US$ 0,70", popular: true },
      { credits: "25", price: "US$ 12,99", unit: "US$ 0,52" },
    ],
    terms: [
      { label: "Primera carta", value: "Gratis", free: true },
      { label: "Cada carta nueva", value: "1 crédito" },
      { label: "La misma carta en otro idioma", value: "Sin costo", free: true },
      { label: "Vencimiento de los créditos", value: "No vencen" },
    ],
    note:
      "Precios en dólares. En tu tienda vas a ver el equivalente en tu moneda, con impuestos incluidos donde correspondan.",
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
  },
  chart: {
    back: "← Tus cartas",
    noWheel: "Esta carta no tiene rueda.",
    noWheelBody: "Se cargó sin hora de nacimiento, así que no hay Ascendente ni casas para orientarla. Las posiciones planetarias sí están.",
    incomplete: "Falta algún cuerpo: su efeméride no cubre esa fecha.",
    interpret: "Leer mi carta",
    interpretCost: "Usa 1 crédito. Después podés leerla en otros idiomas sin costo.",
    interpreting: "Escribiendo tu lectura…",
    readAgain: "Ver la lectura",
    noCredits: "Te quedaste sin créditos.",
    failed: "No pudimos generar la lectura. Probá de nuevo en un rato.",
    columns: { body: "Cuerpo", position: "Posición", house: "Casa" },
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
  auth: {
    navEnter: "Entrar",
    title: "Entrá a tu cuenta.",
    lede: "La misma cuenta que en la app: tus cartas y tus créditos son los mismos.",
    loading: "Cargando…",
    blocked: "No pudimos cargar el acceso de Google. Suele pasar con bloqueadores de rastreadores: desactivalo para este sitio y recargá.",
    failed: "No pudimos iniciar sesión. Probá de nuevo.",
    legal: "Al entrar aceptás los términos y la política de privacidad.",
    credits: "créditos",
    account: "Tu cuenta",
    signOut: "Salir",
    buyCredits: "Sumar créditos",
    buyInApp: "Por ahora los créditos se compran dentro de la app.",
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
      "Your natal chart, computed from real ephemeris and written in your language. Android and iOS.",
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
    items: [
      { meta: "28 Jul 2026 · 7 min", title: "Why an exact birth time changes your whole chart", sign: "☊" },
      { meta: "14 Jul 2026 · 5 min", title: "Sun, Moon and Rising: three things that aren't the same", sign: "☉" },
      { meta: "2 Jul 2026 · 9 min", title: "Mercury retrograde, explained without the mysticism", sign: "☿" },
    ],
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
    title: "Your first chart is free. After that, one credit per chart.",
    colCredits: "Credits",
    colPrice: "Price",
    colUnit: "Per chart",
    popular: "Most chosen",
    packs: [
      { credits: "3", price: "US$ 2.99", unit: "US$ 1.00" },
      { credits: "10", price: "US$ 6.99", unit: "US$ 0.70", popular: true },
      { credits: "25", price: "US$ 12.99", unit: "US$ 0.52" },
    ],
    terms: [
      { label: "First chart", value: "Free", free: true },
      { label: "Each new chart", value: "1 credit" },
      { label: "The same chart in another language", value: "No charge", free: true },
      { label: "Credit expiry", value: "They don't expire" },
    ],
    note:
      "Prices in US dollars. Your store shows the equivalent in your currency, with tax included where it applies.",
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
  },
  chart: {
    back: "← Your charts",
    noWheel: "This chart has no wheel.",
    noWheelBody: "It was entered without a birth time, so there's no Ascendant or houses to orient it. The planetary positions are there.",
    incomplete: "A body is missing: its ephemeris doesn't cover that date.",
    interpret: "Read my chart",
    interpretCost: "Uses 1 credit. After that you can read it in other languages at no cost.",
    interpreting: "Writing your reading…",
    readAgain: "See the reading",
    noCredits: "You've run out of credits.",
    failed: "We couldn't generate the reading. Try again in a while.",
    columns: { body: "Body", position: "Position", house: "House" },
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
  auth: {
    navEnter: "Sign in",
    title: "Sign in to your account.",
    lede: "The same account as in the app: your charts and your credits are the same.",
    loading: "Loading…",
    blocked: "We couldn't load Google sign-in. This usually comes from a tracker blocker: allow this site and reload.",
    failed: "We couldn't sign you in. Try again.",
    legal: "By signing in you accept the terms and the privacy policy.",
    credits: "credits",
    account: "Your account",
    signOut: "Sign out",
    buyCredits: "Add credits",
    buyInApp: "For now, credits are purchased inside the app.",
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
      "Seu mapa natal calculado com efemérides reais e escrito no seu idioma. Android e iOS.",
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
    items: [
      { meta: "28 jul 2026 · 7 min", title: "Por que a hora exata muda o seu mapa inteiro", sign: "☊" },
      { meta: "14 jul 2026 · 5 min", title: "Sol, Lua e Ascendente: três coisas que não são a mesma", sign: "☉" },
      { meta: "2 jul 2026 · 9 min", title: "Mercúrio retrógrado, explicado sem misticismo", sign: "☿" },
    ],
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
    title: "Seu primeiro mapa é grátis. Depois, um crédito por mapa.",
    colCredits: "Créditos",
    colPrice: "Preço",
    colUnit: "Por mapa",
    popular: "Mais escolhido",
    packs: [
      { credits: "3", price: "US$ 2,99", unit: "US$ 1,00" },
      { credits: "10", price: "US$ 6,99", unit: "US$ 0,70", popular: true },
      { credits: "25", price: "US$ 12,99", unit: "US$ 0,52" },
    ],
    terms: [
      { label: "Primeiro mapa", value: "Grátis", free: true },
      { label: "Cada mapa novo", value: "1 crédito" },
      { label: "O mesmo mapa em outro idioma", value: "Sem custo", free: true },
      { label: "Validade dos créditos", value: "Não expiram" },
    ],
    note:
      "Preços em dólares. Na sua loja você vê o equivalente na sua moeda, com impostos incluídos onde se aplicam.",
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
  },
  chart: {
    back: "← Seus mapas",
    noWheel: "Este mapa não tem roda.",
    noWheelBody: "Foi criado sem hora de nascimento, então não há Ascendente nem casas para orientá-la. As posições planetárias estão.",
    incomplete: "Falta algum corpo: a efeméride dele não cobre essa data.",
    interpret: "Ler meu mapa",
    interpretCost: "Usa 1 crédito. Depois você pode lê-lo em outros idiomas sem custo.",
    interpreting: "Escrevendo sua leitura…",
    readAgain: "Ver a leitura",
    noCredits: "Você ficou sem créditos.",
    failed: "Não conseguimos gerar a leitura. Tente de novo daqui a pouco.",
    columns: { body: "Corpo", position: "Posição", house: "Casa" },
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
  auth: {
    navEnter: "Entrar",
    title: "Entre na sua conta.",
    lede: "A mesma conta do app: seus mapas e seus créditos são os mesmos.",
    loading: "Carregando…",
    blocked: "Não conseguimos carregar o acesso do Google. Costuma ser um bloqueador de rastreadores: libere este site e recarregue.",
    failed: "Não conseguimos entrar. Tente de novo.",
    legal: "Ao entrar você aceita os termos e a política de privacidade.",
    credits: "créditos",
    account: "Sua conta",
    signOut: "Sair",
    buyCredits: "Adicionar créditos",
    buyInApp: "Por enquanto os créditos são comprados dentro do app.",
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
