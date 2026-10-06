import type { Locale } from "@/lib/i18n";
import type { MotivoFallo, TipoVinculo } from "@/lib/vinculo";

// Los textos de Vínculo, fase 1. Viven acá y no en `lib/i18n.ts`, que ya pasa
// las 1.500 líneas, y porque son contenido más que rótulos de interfaz.
//
// Escritos sin género y sin suponer pareja: tienen que servir igual para una
// madre y una hija que para dos socios. No prometen compatibilidad ni
// puntaje: la sinastría describe cómo se mueve un vínculo, no lo sentencia.
//
// Los rótulos del formulario que ya existen en `dict.newChart` (fecha, hora,
// lugar, errores de fecha) NO se repiten acá: se reusan, para que las dos
// pantallas no se desincronicen.

export type VinculoCopy = {
  metaTitle: string;
  metaDescription: string;
  eyebrow: string;
  title: string;
  intro: string;
  tipoLabel: string;
  tipos: Record<TipoVinculo, string>;
  personaA: string;
  personaB: string;
  alias: string;
  aliasHint: string;
  calcular: string;
  calculando: string;
  /** Lo que falta cuando una de las dos personas no tiene hora: se dice en vez
   *  de dejar un hueco donde iría la rueda. */
  sinHora: string;
  previewTitle: string;
  /** Antecede al nombre de la persona en el texto alternativo de su rueda. */
  ruedaAlt: string;
  previewLede: string;
  aspectosTitulo: string;
  sinAspectos: string;
  cta: string;
  ctaPronto: string;
  privacidad: string;
  errores: Record<MotivoFallo, string>;
};

export const VINCULO: Record<Locale, VinculoCopy> = {
  es: {
    metaTitle: "Sinastría online: cómo se miran dos cartas natales",
    metaDescription:
      "Compará dos cartas natales: pareja, trabajo, familia o amistad. Mirá gratis las dos ruedas y los aspectos más fuertes entre las dos personas.",
    eyebrow: "Sinastría",
    title: "Cómo se miran dos cartas",
    intro:
      "La sinastría pone una carta natal frente a la otra y mira qué planetas de una persona tocan a los de la otra. No dice si dos personas «son compatibles»: describe cómo se mueve el vínculo, sea de pareja, de trabajo, de familia o de amistad.",
    tipoLabel: "Tipo de vínculo",
    tipos: { pareja: "Pareja", trabajo: "Trabajo", familia: "Familia", amistad: "Amistad" },
    personaA: "Primera persona",
    personaB: "Segunda persona",
    alias: "Cómo le decís (opcional)",
    aliasHint: "Sólo para leerlo vos. No se manda ni se guarda.",
    calcular: "Ver el vínculo",
    calculando: "Calculando…",
    sinHora:
      "Sin la hora de nacimiento de esta persona no hay Ascendente ni casas propias, así que su rueda no se puede dibujar. Los aspectos entre planetas sí están.",
    previewTitle: "Así se miran",
    ruedaAlt: "Rueda natal de",
    previewLede:
      "Las dos ruedas y los contactos más cerrados entre los planetas personales: Sol, Luna, Mercurio, Venus y Marte.",
    aspectosTitulo: "Los contactos más fuertes",
    sinAspectos:
      "Entre los planetas personales no hay contactos cerrados. El vínculo se juega en otro lado —en los planetas lentos y en las casas—, y eso es lo que va a mirar el informe completo.",
    cta: "Leer el vínculo completo",
    ctaPronto: "El informe completo sale en las próximas semanas.",
    privacidad: "No guardamos nada de esto: las dos fechas se usan para calcular y se olvidan.",
    errores: {
      misma_persona:
        "Cargaste los mismos datos para las dos personas. Cambiá la fecha, la hora o el lugar de una de ellas.",
      datos_invalidos: "Revisá las fechas y los lugares: no pudimos calcular con esos datos.",
      demasiadas: "Hay muchos pedidos en este momento. Probá de nuevo más tarde.",
      no_disponible: "No pudimos calcular el vínculo ahora. Probá de nuevo en unos minutos.",
    },
  },
  en: {
    metaTitle: "Synastry chart: how two birth charts meet",
    metaDescription:
      "Compare two birth charts for a couple, work, family or friendship. See both wheels and the strongest aspects between the two people, free.",
    eyebrow: "Synastry",
    title: "How two charts meet",
    intro:
      "Synastry sets one birth chart against another and looks at which planets of one person touch the other's. It doesn't tell you whether two people are “compatible”: it describes how the bond moves, whether it's a couple, work, family or friendship.",
    tipoLabel: "Type of relationship",
    tipos: { pareja: "Couple", trabajo: "Work", familia: "Family", amistad: "Friendship" },
    personaA: "First person",
    personaB: "Second person",
    alias: "What do you call them (optional)",
    aliasHint: "Just for you to read. It isn't sent or stored.",
    calcular: "See the relationship",
    calculando: "Calculating…",
    sinHora:
      "Without this person's birth time there's no Ascendant or houses of their own, so their wheel can't be drawn. The aspects between planets are still there.",
    previewTitle: "How they meet",
    ruedaAlt: "Birth chart wheel of",
    previewLede:
      "Both wheels and the tightest contacts between the personal planets: Sun, Moon, Mercury, Venus and Mars.",
    aspectosTitulo: "The strongest contacts",
    sinAspectos:
      "There are no tight contacts between the personal planets. The relationship plays out elsewhere — in the slow planets and the houses — and that's what the full report will look at.",
    cta: "Read the full relationship",
    ctaPronto: "The full report comes out in the next few weeks.",
    privacidad: "We don't store any of this: both dates are used to compute and then forgotten.",
    errores: {
      misma_persona:
        "You entered the same details for both people. Change the date, time or place for one of them.",
      datos_invalidos: "Check the dates and places: we couldn't compute with those details.",
      demasiadas: "There are a lot of requests right now. Please try again later.",
      no_disponible: "We couldn't compute the relationship right now. Please try again in a few minutes.",
    },
  },
  pt: {
    metaTitle: "Sinastria online: como dois mapas natais se encontram",
    metaDescription:
      "Compare dois mapas natais: casal, trabalho, família ou amizade. Veja de graça as duas rodas e os aspectos mais fortes entre as duas pessoas.",
    eyebrow: "Sinastria",
    title: "Como dois mapas se encontram",
    intro:
      "A sinastria coloca um mapa natal diante do outro e observa quais planetas de uma pessoa tocam os da outra. Ela não diz se duas pessoas «são compatíveis»: descreve como o vínculo se move, seja de casal, de trabalho, de família ou de amizade.",
    tipoLabel: "Tipo de vínculo",
    tipos: { pareja: "Casal", trabajo: "Trabalho", familia: "Família", amistad: "Amizade" },
    personaA: "Primeira pessoa",
    personaB: "Segunda pessoa",
    alias: "Como você a chama (opcional)",
    aliasHint: "Só para você ler. Não é enviado nem guardado.",
    calcular: "Ver o vínculo",
    calculando: "Calculando…",
    sinHora:
      "Sem a hora de nascimento desta pessoa não há Ascendente nem casas próprias, então a roda dela não pode ser desenhada. Os aspectos entre planetas continuam aí.",
    previewTitle: "Assim se encontram",
    ruedaAlt: "Roda natal de",
    previewLede:
      "As duas rodas e os contatos mais fechados entre os planetas pessoais: Sol, Lua, Mercúrio, Vênus e Marte.",
    aspectosTitulo: "Os contatos mais fortes",
    sinAspectos:
      "Entre os planetas pessoais não há contatos fechados. O vínculo se joga em outro lugar — nos planetas lentos e nas casas — e é isso que o relatório completo vai olhar.",
    cta: "Ler o vínculo completo",
    ctaPronto: "O relatório completo sai nas próximas semanas.",
    privacidad: "Não guardamos nada disso: as duas datas são usadas para calcular e esquecidas.",
    errores: {
      misma_persona:
        "Você informou os mesmos dados para as duas pessoas. Mude a data, a hora ou o lugar de uma delas.",
      datos_invalidos: "Confira as datas e os lugares: não conseguimos calcular com esses dados.",
      demasiadas: "Há muitos pedidos neste momento. Tente de novo mais tarde.",
      no_disponible: "Não conseguimos calcular o vínculo agora. Tente de novo em alguns minutos.",
    },
  },
};
