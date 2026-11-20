import type { Dict, Locale } from "@/lib/i18n";

// Los textos del diccionario que cambian en modo vidriera. El diccionario
// describe el sitio vendiendo: habla de cuentas, de guardar cartas y de un
// informe que se paga. En la vidriera nada de eso existe, y dejarlo escrito
// le promete al visitante algo que después responde 404.
//
// Acá va sólo lo que se ve en las páginas que quedan abiertas (home, /nueva y
// la carta calculada). Lo de precios, compra, cuenta y acceso no se toca: esas
// páginas no se sirven. `getDict` aplica estos cambios; apagado el modo,
// devuelve el diccionario de siempre.

type Pregunta = { q: string; a: string };

type Cambios = {
  privacidadTitulo: string;
  /** Reemplaza al tercer punto de privacidad («Borrar es borrar»). */
  sinCuentas: { strong: string; rest: string };
  /** Respuesta de «¿En qué idiomas está?»: la original habla de costo. */
  idiomas: string;
  /** Reemplazan a las tres preguntas sobre cuentas. */
  preguntas: Pregunta[];
  previewPrivacidad: string;
  seoGratis: string;
  seoGratisBody: string;
};

const CAMBIOS: Record<Locale, Cambios> = {
  es: {
    privacidadTitulo: "Tus datos de nacimiento no se guardan.",
    sinCuentas: {
      strong: "No hay nada que borrar.",
      rest: "Este sitio no tiene cuentas: la carta se calcula en el momento y no queda copia en nuestros servidores.",
    },
    idiomas: "Español, inglés y portugués: la carta, las notas y la lectura de ejemplo están en los tres.",
    preguntas: [
      {
        q: "¿Necesito crear una cuenta?",
        a: "No. Este sitio es una muestra y no tiene cuentas ni registro: ponés tus datos y ves tu carta.",
      },
      {
        q: "¿Puedo hacer cartas de otras personas?",
        a: "Sí, las que quieras. Cada carta se calcula en el momento con los datos que cargues.",
      },
      {
        q: "¿Se guardan mis datos de nacimiento?",
        a: "No. La fecha, la hora y el lugar se usan para calcular la carta en el momento y no quedan guardados en nuestros servidores.",
      },
      {
        q: "¿Se puede comprar el informe completo?",
        a: "Ya no. ASTRA se vendió hasta noviembre de 2026 y hoy queda como muestra de trabajo de dothecode. La carta de ejemplo muestra cómo es una lectura.",
      },
    ],
    previewPrivacidad:
      "Tus datos de nacimiento no se guardan en nuestros servidores: la carta se calcula en el momento.",
    seoGratis: "Qué vas a ver",
    seoGratisBody:
      "Tu carta completa y un adelanto de lo que diría tu informe, sin cuenta y sin pagar nada. El informe completo ya no se vende; la carta de ejemplo muestra cómo es una lectura.",
  },
  en: {
    privacidadTitulo: "Your birth details are not stored.",
    sinCuentas: {
      strong: "There is nothing to delete.",
      rest: "This site has no accounts: your chart is calculated on the spot and no copy is kept on our servers.",
    },
    idiomas: "Spanish, English and Portuguese: the chart, the notes and the sample reading are available in all three.",
    preguntas: [
      {
        q: "Do I need an account?",
        a: "No. This is a showcase site with no accounts and no sign-up: you enter your details and see your chart.",
      },
      {
        q: "Can I make charts for other people?",
        a: "Yes, as many as you like. Each chart is calculated on the spot from the details you enter.",
      },
      {
        q: "Are my birth details stored?",
        a: "No. Your date, time and place are used to calculate the chart on the spot and are not kept on our servers.",
      },
      {
        q: "Can I buy the full report?",
        a: "Not anymore. ASTRA was on sale until November 2026 and now stays online as a dothecode showcase. The sample chart shows what a reading looks like.",
      },
    ],
    previewPrivacidad: "Your birth details are not stored on our servers: the chart is calculated on the spot.",
    seoGratis: "What you will see",
    seoGratisBody:
      "Your full chart and a preview of what your report would say, with no account and nothing to pay. The full report is no longer on sale; the sample chart shows what a reading looks like.",
  },
  pt: {
    privacidadTitulo: "Seus dados de nascimento não são guardados.",
    sinCuentas: {
      strong: "Não há nada para apagar.",
      rest: "Este site não tem contas: o mapa é calculado na hora e nenhuma cópia fica nos nossos servidores.",
    },
    idiomas: "Espanhol, inglês e português: o mapa, as notas e a leitura de exemplo estão nos três.",
    preguntas: [
      {
        q: "Preciso criar uma conta?",
        a: "Não. Este site é uma demonstração e não tem contas nem cadastro: você informa seus dados e vê seu mapa.",
      },
      {
        q: "Posso fazer mapas de outras pessoas?",
        a: "Sim, quantos quiser. Cada mapa é calculado na hora com os dados que você informar.",
      },
      {
        q: "Meus dados de nascimento ficam guardados?",
        a: "Não. A data, a hora e o local são usados para calcular o mapa na hora e não ficam guardados nos nossos servidores.",
      },
      {
        q: "Dá para comprar o relatório completo?",
        a: "Não mais. O ASTRA foi vendido até novembro de 2026 e hoje fica como demonstração de trabalho da dothecode. O mapa de exemplo mostra como é uma leitura.",
      },
    ],
    previewPrivacidad:
      "Seus dados de nascimento não ficam guardados nos nossos servidores: o mapa é calculado na hora.",
    seoGratis: "O que você vai ver",
    seoGratisBody:
      "Seu mapa completo e uma prévia do que diria o seu relatório, sem conta e sem pagar nada. O relatório completo não é mais vendido; o mapa de exemplo mostra como é uma leitura.",
  },
};

/** Cuántas preguntas del diccionario se conservan: hora, idiomas y cálculo.
 *  Las que siguen son las de cuentas, que la vidriera reemplaza. */
const PREGUNTAS_QUE_QUEDAN = 3;
const PREGUNTA_IDIOMAS = 1;

export function dictDeVidriera(dict: Dict, locale: Locale): Dict {
  const c = CAMBIOS[locale];
  const quedan = dict.faq.items
    .slice(0, PREGUNTAS_QUE_QUEDAN)
    .map((item, i) => (i === PREGUNTA_IDIOMAS ? { ...item, a: c.idiomas } : item));
  return {
    ...dict,
    privacy: {
      ...dict.privacy,
      title: c.privacidadTitulo,
      points: [...dict.privacy.points.slice(0, 2), c.sinCuentas],
    },
    faq: { ...dict.faq, items: [...quedan, ...c.preguntas] },
    newChart: {
      ...dict.newChart,
      previewPrivacidad: c.previewPrivacidad,
      seoGratis: c.seoGratis,
      seoGratisBody: c.seoGratisBody,
    },
  };
}
