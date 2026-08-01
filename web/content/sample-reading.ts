import type { Locale } from "@/lib/i18n";

// La lectura de la carta de ejemplo. Cada pasaje declara de qué dato del cálculo
// sale: ese vínculo entre el número y la frase es el producto. Sin él, esto sería
// un horóscopo de revista.

export type SampleReading = {
  eyebrow: string;
  pageTitle: string;
  back: string;
  columns: { body: string; position: string; house: string };
  legend: { soft: string; hard: string; axes: string };
  opening: string;
  passages: { source: string; paragraphs: string[] }[];
  closing: { title: string; note: string; cta: string };
  disclaimer: string;
  wheelAlt: string;
};

const es: SampleReading = {
  eyebrow: "Carta de ejemplo",
  pageTitle: "Carta de ejemplo",
  back: "← Volver",
  columns: { body: "Cuerpo", position: "Posición", house: "Casa" },
  legend: {
    soft: "Armónicos · trígono, sextil",
    hard: "Tensos · cuadratura, oposición",
    axes: "Ejes",
  },
  opening:
    "Cuatro cuerpos en Piscis y el Ascendente en el mismo signo. Esta es una carta que empieza por lo que no se dice en voz alta.",
  passages: [
    {
      source: "☉ Sol 21°36′ ♓ · ☽ Luna 23°07′ ♓ · Casa 12",
      paragraphs: [
        "Naciste con el Sol y la Luna a un grado y medio de distancia, los dos en Piscis y los dos en la casa doce. Es una luna nueva, o casi: quien sos y lo que sentís apuntan al mismo lado, sin ese tironeo interno que aparece en las cartas donde el Sol y la Luna se miran de lejos.",
        "La casa doce le pone el matiz. Es el sector de la carta donde las cosas pasan puertas adentro, antes de tener nombre. Nada de esto habla de aislamiento: habla de que tu procesamiento va varios pasos adelante de tu explicación, y que solés entender lo que te pasó bastante después de que te pasó.",
      ],
    },
    {
      source: "ASC 27°00′ ♓ · ♀ Venus 4°45′ ♈ · Casa 1",
      paragraphs: [
        "El Ascendente está en los últimos grados de Piscis, a punto de cambiar de signo, y Venus ya cruzó: está en Aries, dentro de tu casa uno. Esa combinación explica una contradicción que probablemente te señalaron alguna vez. La primera impresión que das es suave, permeable, difícil de encasillar. Y sin embargo, cuando algo te importa, vas de frente y sin rodeos.",
        "No son dos personas. Es un umbral: la carta te agarró justo en el momento en que Piscis termina y Aries empieza.",
      ],
    },
    {
      source: "♃ Júpiter 14°26′ ♏ ℞ · Casa 8 · Trígono al Sol",
      paragraphs: [
        "Júpiter retrógrado en Escorpio, en la casa ocho, en trígono con tu Sol. Júpiter expande lo que toca, y acá toca el terreno de lo que se comparte y de lo que se transforma: los vínculos profundos, el dinero que no es sólo tuyo, los finales.",
        "Retrógrado significa que ese crecimiento no te llega de afuera, ni por golpes de suerte visibles. Llega cuando revisás. El trígono con el Sol dice que cuando lo hacés, la carta entera se acomoda.",
      ],
    },
  ],
  closing: {
    title: "Tu carta sale del mismo cálculo.",
    note: "Fecha, hora y lugar de nacimiento. La primera lectura no cuesta nada y leerla en otro idioma tampoco.",
    cta: "Calcular mi carta",
  },
  disclaimer:
    "Camila es un ejemplo: los datos de nacimiento son inventados, pero las posiciones, las casas y los aspectos son los que devuelve el cálculo real para esa fecha, esa hora y ese lugar. Las lecturas de ASTRA son para entretenimiento y autoconocimiento; no son consejo médico, legal ni financiero.",
  wheelAlt: "Rueda natal de la carta de ejemplo, con las doce casas, los planetas y sus aspectos",
};

const en: SampleReading = {
  eyebrow: "Sample chart",
  pageTitle: "Sample chart",
  back: "← Back",
  columns: { body: "Body", position: "Position", house: "House" },
  legend: {
    soft: "Harmonious · trine, sextile",
    hard: "Tense · square, opposition",
    axes: "Axes",
  },
  opening:
    "Four bodies in Pisces and the Ascendant in the same sign. This is a chart that begins with what goes unsaid.",
  passages: [
    {
      source: "☉ Sun 21°36′ ♓ · ☽ Moon 23°07′ ♓ · House 12",
      paragraphs: [
        "You were born with the Sun and the Moon a degree and a half apart, both in Pisces and both in the twelfth house. That's a new moon, or nearly: who you are and what you feel point the same way, without the inner tug-of-war you find in charts where the Sun and the Moon watch each other from a distance.",
        "The twelfth house adds the nuance. It's the sector where things happen behind closed doors, before they have a name. None of this is about isolation: it's that your processing runs several steps ahead of your explanation, and you tend to understand what happened to you well after it happened.",
      ],
    },
    {
      source: "ASC 27°00′ ♓ · ♀ Venus 4°45′ ♈ · House 1",
      paragraphs: [
        "The Ascendant sits in the last degrees of Pisces, about to change sign, and Venus has already crossed: it's in Aries, inside your first house. That combination explains a contradiction someone has probably pointed out to you. The first impression you give is soft, permeable, hard to pin down. And yet, when something matters to you, you go straight at it.",
        "They aren't two people. It's a threshold: the chart caught you exactly where Pisces ends and Aries begins.",
      ],
    },
    {
      source: "♃ Jupiter 14°26′ ♏ ℞ · House 8 · Trine to the Sun",
      paragraphs: [
        "Jupiter retrograde in Scorpio, in the eighth house, trine your Sun. Jupiter expands whatever it touches, and here it touches the ground of what is shared and what is transformed: deep bonds, money that isn't only yours, endings.",
        "Retrograde means that growth doesn't reach you from outside, or through visible strokes of luck. It arrives when you go back over things. The trine to the Sun says that when you do, the whole chart settles.",
      ],
    },
  ],
  closing: {
    title: "Your chart comes from the same calculation.",
    note: "Birth date, time and place. The first reading costs nothing, and reading it in another language doesn't either.",
    cta: "Compute my chart",
  },
  disclaimer:
    "Camila is an example: the birth details are invented, but the positions, houses and aspects are what the real calculation returns for that date, time and place. ASTRA's readings are for entertainment and self-reflection; they are not medical, legal or financial advice.",
  wheelAlt: "Natal wheel of the sample chart, with the twelve houses, the planets and their aspects",
};

const pt: SampleReading = {
  eyebrow: "Mapa de exemplo",
  pageTitle: "Mapa de exemplo",
  back: "← Voltar",
  columns: { body: "Corpo", position: "Posição", house: "Casa" },
  legend: {
    soft: "Harmônicos · trígono, sextil",
    hard: "Tensos · quadratura, oposição",
    axes: "Eixos",
  },
  opening:
    "Quatro corpos em Peixes e o Ascendente no mesmo signo. Este é um mapa que começa pelo que não se diz em voz alta.",
  passages: [
    {
      source: "☉ Sol 21°36′ ♓ · ☽ Lua 23°07′ ♓ · Casa 12",
      paragraphs: [
        "Você nasceu com o Sol e a Lua a um grau e meio de distância, os dois em Peixes e os dois na casa doze. É uma lua nova, ou quase: quem você é e o que você sente apontam para o mesmo lado, sem aquele puxa-empurra interno que aparece nos mapas em que o Sol e a Lua se olham de longe.",
        "A casa doze dá o matiz. É o setor do mapa onde as coisas acontecem portas adentro, antes de terem nome. Nada disso fala de isolamento: fala de que o seu processamento vai vários passos à frente da sua explicação, e que você costuma entender o que aconteceu bem depois de ter acontecido.",
      ],
    },
    {
      source: "ASC 27°00′ ♓ · ♀ Vênus 4°45′ ♈ · Casa 1",
      paragraphs: [
        "O Ascendente está nos últimos graus de Peixes, prestes a mudar de signo, e Vênus já cruzou: está em Áries, dentro da sua casa um. Essa combinação explica uma contradição que provavelmente já apontaram em você. A primeira impressão que você passa é suave, permeável, difícil de rotular. E, no entanto, quando algo importa, você vai de frente.",
        "Não são duas pessoas. É um limiar: o mapa pegou você bem no momento em que Peixes termina e Áries começa.",
      ],
    },
    {
      source: "♃ Júpiter 14°26′ ♏ ℞ · Casa 8 · Trígono ao Sol",
      paragraphs: [
        "Júpiter retrógrado em Escorpião, na casa oito, em trígono com o seu Sol. Júpiter expande o que toca, e aqui toca o terreno do que se compartilha e do que se transforma: os vínculos profundos, o dinheiro que não é só seu, os finais.",
        "Retrógrado significa que esse crescimento não chega de fora, nem por golpes de sorte visíveis. Chega quando você revisa. O trígono com o Sol diz que, quando você faz isso, o mapa inteiro se acomoda.",
      ],
    },
  ],
  closing: {
    title: "Seu mapa sai do mesmo cálculo.",
    note: "Data, hora e local de nascimento. A primeira leitura não custa nada, e lê-la em outro idioma também não.",
    cta: "Calcular meu mapa",
  },
  disclaimer:
    "Camila é um exemplo: os dados de nascimento são inventados, mas as posições, as casas e os aspectos são os que o cálculo real devolve para aquela data, hora e lugar. As leituras do ASTRA são para entretenimento e autoconhecimento; não são aconselhamento médico, jurídico nem financeiro.",
  wheelAlt: "Roda natal do mapa de exemplo, com as doze casas, os planetas e seus aspectos",
};

export const SAMPLE_READING: Record<Locale, SampleReading> = { es, en, pt };
