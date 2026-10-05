import type { Locale } from "@/lib/i18n";

// Los textos de «el cielo de hoy». Viven acá y no en `lib/i18n.ts`, que ya pasa
// las 1.500 líneas, y porque son contenido —los doce párrafos de la Luna por
// signo— más que rótulos de interfaz.
//
// Escritos una vez y revisados a mano: la página tiene que darle a Google texto
// que leer, pero no puede ser texto generado en masa, que es justo lo que su
// política contra el contenido automatizado castiga.

/** Las cuatro fases principales, con las claves que devuelve `/api/sky/moon/`. */
export type MajorPhase = "new_moon" | "first_quarter" | "full_moon" | "last_quarter";

/** Las ocho fases de kerykeion, en snake_case. */
export type Phase =
  | MajorPhase
  | "waxing_crescent"
  | "waxing_gibbous"
  | "waning_gibbous"
  | "waning_crescent";

export type CieloCopy = {
  /** La entrada del nav. */
  nav: string;
  /** `<title>` y `<h1>`. */
  metaTitle: string;
  metaDescription: string;
  eyebrow: string;
  title: string;
  /** Debajo del título, antes del instante del cálculo. */
  computedAt: string;
  lede: string;
  wheelAlt: string;

  moonHeading: string;
  /** «La Luna está en Leo, a 12°04′.» */
  moonIn: (sign: string, degree: string) => string;
  phaseNames: Record<Phase, string>;
  /** Sigue al nombre de la fase: «Luna menguante, con el 34 % del disco
   *  iluminado.» No repite si crece o mengua: el nombre de la fase ya lo dice. */
  illumination: (percent: number) => string;
  /** «Entra en Virgo el» — sigue la fecha. */
  entersSign: (sign: string) => string;
  /** Un párrafo por signo, en el orden del zodíaco. */
  moonSigns: string[];

  nextPhasesHeading: string;

  retroHeading: string;
  retroNone: string;
  retroSome: string;
  retroExplain: string;

  tableHeading: string;
  columns: { body: string; position: string };
  retroMark: string;

  /** Cuando el navegador todavía no convirtió las horas a la zona local. */
  timesInUtc: string;
  timesLocal: string;

  closing: { title: string; note: string; cta: string };
};

const es: CieloCopy = {
  nav: "Cielo de hoy",
  metaTitle: "La Luna hoy y el cielo de este momento",
  metaDescription:
    "En qué signo está la Luna hoy, su fase e iluminación, cuándo cambia de signo, las próximas lunas llena y nueva, y qué planetas están retrógrados. Calculado con Swiss Ephemeris.",
  eyebrow: "Efemérides de hoy",
  title: "El cielo de hoy",
  computedAt: "Calculado para",
  lede:
    "Las posiciones son las de este momento, con las mismas efemérides que ASTRA usa para las cartas natales. Son geocéntricas, así que valen igual en cualquier lugar del mundo: lo único que cambia con tu zona es la hora.",
  wheelAlt: "Rueda zodiacal con la posición actual del Sol, la Luna y los planetas",

  moonHeading: "La Luna hoy",
  moonIn: (sign, degree) => `La Luna está en ${sign}, a ${degree}.`,
  phaseNames: {
    new_moon: "Luna nueva",
    waxing_crescent: "Luna creciente",
    first_quarter: "Cuarto creciente",
    waxing_gibbous: "Gibosa creciente",
    full_moon: "Luna llena",
    waning_gibbous: "Gibosa menguante",
    last_quarter: "Cuarto menguante",
    waning_crescent: "Luna menguante",
  },
  illumination: (percent) => `, con el ${percent}\u00a0% del disco iluminado.`,
  entersSign: (sign) => `Entra en ${sign} el`,
  moonSigns: [
    "La Luna en Aries pone el ánimo en marcha: reacciones rápidas, poca paciencia y ganas de empezar cosas más que de terminarlas. Es un tránsito corto y encendido, bueno para dar el primer paso y malo para las conversaciones delicadas.",
    "En Tauro la Luna busca lo que se puede tocar: comida, descanso, el cuerpo, el dinero propio. Baja el ritmo y vuelve las cosas más estables y más tercas. Se disfruta lo que ya está; cuesta cambiar de planes.",
    "La Luna en Géminis llena el día de mensajes, conversaciones y cambios de tema. La curiosidad está alta y la atención es corta. Rinde para aprender, escribir y conectar gente; no tanto para concentrarse en una sola cosa.",
    "Cáncer es el signo propio de la Luna, y acá se nota: el ánimo se vuelve más sensible, más hogareño y más pendiente de los suyos. La memoria emocional está a flor de piel. Es tiempo de cuidar y de dejarse cuidar.",
    "En Leo la Luna quiere que se la vea. Sube la necesidad de reconocimiento, de juego y de expresarse con algo de teatro. Es generosa y cálida, y también se ofende más fácil si siente que no la tienen en cuenta.",
    "La Luna en Virgo ordena. Aparecen las listas, los detalles y las ganas de arreglar lo que está torcido, empezando por la rutina y el cuerpo. Es buena para el trabajo minucioso; el riesgo es la autocrítica de más.",
    "En Libra la Luna busca acuerdo y armonía: importa cómo se dicen las cosas y con quién se está. Es un buen momento para negociar, acompañar y embellecer. Cuesta decidir sola y cuesta decir que no.",
    "La Luna en Escorpio va al fondo. Las emociones se vuelven intensas, privadas y difíciles de disimular, y aparece el olfato para lo que no se dice. Es un tránsito para la verdad y la transformación, no para lo superficial.",
    "En Sagitario la Luna pide aire: viajes, ideas grandes, conversaciones que abren el panorama. El ánimo es optimista y franco, a veces demasiado. Rinde para planear y enseñar; aburren los detalles.",
    "La Luna en Capricornio se pone seria. Las emociones pasan a segundo plano frente a lo que hay que hacer, y aparece una necesidad de estructura y de resultados. Es buena para comprometerse y cumplir; puede sentirse fría.",
    "En Acuario la Luna se distancia un poco de lo personal para mirar el conjunto: amistades, grupos, causas, lo que viene. El ánimo es inventivo y algo imprevisible. Se necesita espacio propio más que contención.",
    "La Luna en Piscis disuelve los bordes. Sube la sensibilidad, la intuición y la empatía, y también el cansancio y la dispersión. Es un buen tránsito para el arte, el descanso y la compasión; malo para las fechas límite.",
  ],

  nextPhasesHeading: "Próximas fases",

  retroHeading: "Planetas retrógrados",
  retroNone: "Ahora mismo no hay ningún planeta retrógrado.",
  retroSome: "Ahora mismo están retrógrados:",
  retroExplain:
    "Un planeta está retrógrado cuando, visto desde la Tierra, parece moverse hacia atrás en el zodíaco. Es un efecto de perspectiva —la Tierra lo pasa o él pasa a la Tierra en su órbita—, y en astrología se lee como un tiempo para revisar, retomar y corregir lo que ese planeta representa. El Sol y la Luna nunca están retrógrados.",

  tableHeading: "Posiciones de este momento",
  columns: { body: "Cuerpo", position: "Posición" },
  retroMark: "retrógrado",

  timesInUtc: "Horas en UTC.",
  timesLocal: "Horas en tu zona horaria.",

  closing: {
    title: "¿Y en tu carta?",
    note: "El cielo de hoy es el mismo para todos. El de tu nacimiento es sólo tuyo: calculalo gratis con tu fecha, hora y lugar.",
    cta: "Calcular mi carta natal",
  },
};

const en: CieloCopy = {
  nav: "Sky today",
  metaTitle: "The Moon today and the sky right now",
  metaDescription:
    "What sign the Moon is in today, its phase and illumination, when it changes sign, the next full and new moons, and which planets are retrograde. Calculated with Swiss Ephemeris.",
  eyebrow: "Today's ephemeris",
  title: "The sky today",
  computedAt: "Calculated for",
  lede:
    "These are the positions for this moment, from the same ephemeris ASTRA uses for birth charts. They are geocentric, so they hold anywhere in the world: the only thing your time zone changes is the clock time.",
  wheelAlt: "Zodiac wheel showing the current position of the Sun, the Moon and the planets",

  moonHeading: "The Moon today",
  moonIn: (sign, degree) => `The Moon is in ${sign}, at ${degree}.`,
  phaseNames: {
    new_moon: "New moon",
    waxing_crescent: "Waxing crescent",
    first_quarter: "First quarter",
    waxing_gibbous: "Waxing gibbous",
    full_moon: "Full moon",
    waning_gibbous: "Waning gibbous",
    last_quarter: "Last quarter",
    waning_crescent: "Waning crescent",
  },
  illumination: (percent) => `, with ${percent}% of the disc lit.`,
  entersSign: (sign) => `Enters ${sign} on`,
  moonSigns: [
    "The Moon in Aries gets things moving: quick reactions, little patience and more appetite for starting than finishing. It is a short, fiery transit, good for taking the first step and poor for delicate conversations.",
    "In Taurus the Moon looks for what can be touched: food, rest, the body, one's own money. The pace slows and things become steadier and more stubborn. What is already there is enjoyed; changing plans is hard.",
    "The Moon in Gemini fills the day with messages, conversations and changes of subject. Curiosity runs high and attention runs short. It is good for learning, writing and connecting people, less so for focusing on one thing.",
    "Cancer is the Moon's own sign, and it shows: moods grow more sensitive, more home-bound and more attentive to one's people. Emotional memory sits close to the surface. It is a time to care for others and let yourself be cared for.",
    "In Leo the Moon wants to be seen. The need for recognition, play and expressing oneself with a bit of theatre rises. It is warm and generous, and also quicker to take offence when it feels overlooked.",
    "The Moon in Virgo tidies up. Lists, details and the urge to fix what is crooked appear, starting with routine and the body. It suits careful work; the risk is too much self-criticism.",
    "In Libra the Moon seeks agreement and harmony: how things are said, and with whom, matters. It is a good moment to negotiate, keep company and make things beautiful. Deciding alone and saying no are harder.",
    "The Moon in Scorpio goes deep. Emotions become intense, private and hard to hide, and there is a nose for what goes unsaid. It is a transit for truth and transformation, not for the superficial.",
    "In Sagittarius the Moon asks for air: travel, big ideas, conversations that widen the view. The mood is optimistic and frank, sometimes too much so. It is good for planning and teaching; details bore it.",
    "The Moon in Capricorn turns serious. Feelings take a back seat to what needs doing, and a need for structure and results appears. It is good for committing and delivering; it can feel cold.",
    "In Aquarius the Moon steps back from the personal to look at the whole: friends, groups, causes, what is coming. The mood is inventive and a little unpredictable. Room of one's own matters more than comfort.",
    "The Moon in Pisces dissolves the edges. Sensitivity, intuition and empathy rise, and so do tiredness and distraction. It is a good transit for art, rest and compassion; a bad one for deadlines.",
  ],

  nextPhasesHeading: "Upcoming phases",

  retroHeading: "Retrograde planets",
  retroNone: "No planet is retrograde right now.",
  retroSome: "Retrograde right now:",
  retroExplain:
    "A planet is retrograde when, seen from Earth, it appears to move backwards through the zodiac. It is an effect of perspective —Earth overtakes it, or it overtakes Earth, in their orbits— and astrology reads it as a time to review, revisit and correct what that planet stands for. The Sun and the Moon are never retrograde.",

  tableHeading: "Positions right now",
  columns: { body: "Body", position: "Position" },
  retroMark: "retrograde",

  timesInUtc: "Times in UTC.",
  timesLocal: "Times in your time zone.",

  closing: {
    title: "And in your chart?",
    note: "Today's sky is the same for everyone. The one you were born under is yours alone: calculate it for free with your date, time and place.",
    cta: "Calculate my birth chart",
  },
};

const pt: CieloCopy = {
  nav: "Céu de hoje",
  metaTitle: "A Lua hoje e o céu deste momento",
  metaDescription:
    "Em que signo está a Lua hoje, sua fase e iluminação, quando muda de signo, as próximas luas cheia e nova, e quais planetas estão retrógrados. Calculado com Swiss Ephemeris.",
  eyebrow: "Efemérides de hoje",
  title: "O céu de hoje",
  computedAt: "Calculado para",
  lede:
    "As posições são as deste momento, com as mesmas efemérides que a ASTRA usa para os mapas natais. São geocêntricas, então valem igual em qualquer lugar do mundo: a única coisa que muda com o seu fuso é o horário.",
  wheelAlt: "Roda zodiacal com a posição atual do Sol, da Lua e dos planetas",

  moonHeading: "A Lua hoje",
  moonIn: (sign, degree) => `A Lua está em ${sign}, a ${degree}.`,
  phaseNames: {
    new_moon: "Lua nova",
    waxing_crescent: "Lua crescente",
    first_quarter: "Quarto crescente",
    waxing_gibbous: "Gibosa crescente",
    full_moon: "Lua cheia",
    waning_gibbous: "Gibosa minguante",
    last_quarter: "Quarto minguante",
    waning_crescent: "Lua minguante",
  },
  illumination: (percent) => `, com ${percent}% do disco iluminado.`,
  entersSign: (sign) => `Entra em ${sign} em`,
  moonSigns: [
    "A Lua em Áries põe o ânimo em movimento: reações rápidas, pouca paciência e mais vontade de começar do que de terminar. É um trânsito curto e aceso, bom para dar o primeiro passo e ruim para conversas delicadas.",
    "Em Touro a Lua procura o que dá para tocar: comida, descanso, o corpo, o próprio dinheiro. O ritmo diminui e as coisas ficam mais estáveis e mais teimosas. Aproveita-se o que já existe; mudar de planos custa.",
    "A Lua em Gêmeos enche o dia de mensagens, conversas e mudanças de assunto. A curiosidade está alta e a atenção, curta. Rende para aprender, escrever e conectar pessoas; nem tanto para se concentrar numa coisa só.",
    "Câncer é o signo da própria Lua, e isso se nota: o ânimo fica mais sensível, mais caseiro e mais atento aos seus. A memória emocional está à flor da pele. É tempo de cuidar e de se deixar cuidar.",
    "Em Leão a Lua quer ser vista. Sobe a necessidade de reconhecimento, de brincadeira e de se expressar com um pouco de teatro. É generosa e calorosa, e também se ofende mais fácil se sente que não foi levada em conta.",
    "A Lua em Virgem organiza. Aparecem as listas, os detalhes e a vontade de consertar o que está torto, começando pela rotina e pelo corpo. É boa para o trabalho minucioso; o risco é a autocrítica em excesso.",
    "Em Libra a Lua busca acordo e harmonia: importa como as coisas são ditas e com quem se está. É um bom momento para negociar, acompanhar e embelezar. Custa decidir sozinha e custa dizer não.",
    "A Lua em Escorpião vai fundo. As emoções ficam intensas, reservadas e difíceis de disfarçar, e aparece o faro para o que não é dito. É um trânsito para a verdade e a transformação, não para o superficial.",
    "Em Sagitário a Lua pede ar: viagens, ideias grandes, conversas que abrem o horizonte. O ânimo é otimista e franco, às vezes demais. Rende para planejar e ensinar; os detalhes entediam.",
    "A Lua em Capricórnio fica séria. As emoções passam para o segundo plano diante do que precisa ser feito, e aparece uma necessidade de estrutura e de resultados. É boa para se comprometer e cumprir; pode parecer fria.",
    "Em Aquário a Lua se afasta um pouco do pessoal para olhar o conjunto: amizades, grupos, causas, o que vem por aí. O ânimo é inventivo e um tanto imprevisível. Precisa-se mais de espaço próprio do que de acolhimento.",
    "A Lua em Peixes dissolve as bordas. Sobem a sensibilidade, a intuição e a empatia, e também o cansaço e a dispersão. É um bom trânsito para a arte, o descanso e a compaixão; ruim para prazos.",
  ],

  nextPhasesHeading: "Próximas fases",

  retroHeading: "Planetas retrógrados",
  retroNone: "Neste momento nenhum planeta está retrógrado.",
  retroSome: "Neste momento estão retrógrados:",
  retroExplain:
    "Um planeta está retrógrado quando, visto da Terra, parece andar para trás no zodíaco. É um efeito de perspectiva —a Terra o ultrapassa, ou ele ultrapassa a Terra, nas suas órbitas—, e a astrologia o lê como um tempo para revisar, retomar e corrigir o que esse planeta representa. O Sol e a Lua nunca ficam retrógrados.",

  tableHeading: "Posições deste momento",
  columns: { body: "Corpo", position: "Posição" },
  retroMark: "retrógrado",

  timesInUtc: "Horários em UTC.",
  timesLocal: "Horários no seu fuso.",

  closing: {
    title: "E no seu mapa?",
    note: "O céu de hoje é o mesmo para todos. O do seu nascimento é só seu: calcule grátis com a sua data, hora e local.",
    cta: "Calcular meu mapa natal",
  },
};

export const CIELO: Record<Locale, CieloCopy> = { es, en, pt };
