import { LOCALES, type Locale } from "@/lib/i18n";

// Modo vidriera: el sitio como muestra de trabajo, sin cobro ni cuentas.
//
// Es una variable de build (`NEXT_PUBLIC_VIDRIERA=1`) y no una consulta al
// backend: casi todas las páginas se generan al compilar, cuando el backend no
// está, y un flag leído en ese momento saldría siempre apagado. El backend
// tiene el suyo (`MODO_VIDRIERA`) y los dos fallan para el lado seguro: con
// sólo el de la web prendido se esconden botones que andarían; con sólo el del
// backend, un botón visible recibe un 404.
//
// Se lee en cada llamada y con el nombre completo escrito: Next reemplaza
// `process.env.NEXT_PUBLIC_*` por su valor al compilar, y sólo lo hace si la
// expresión aparece literal.
export function esVidriera(): boolean {
  return process.env.NEXT_PUBLIC_VIDRIERA === "1";
}

/** Primer segmento (después del idioma) de las páginas que sólo sirven para
 *  comprar o para entrar a una cuenta. En vidriera responden 404 (`proxy.ts`). */
const SECCIONES_CERRADAS = new Set(["entrar", "precios", "cuenta", "compra", "arrepentimiento", "carta"]);

export function cerradaEnVidriera(pathname: string): boolean {
  const [vacio, locale, seccion] = pathname.split("/");
  return vacio === "" && (LOCALES as readonly string[]).includes(locale) && SECCIONES_CERRADAS.has(seccion ?? "");
}

/** Los textos propios del modo. Acá y no en el diccionario: son frases que
 *  sólo existen en la vidriera. Los del diccionario que cambian con el modo
 *  están en `lib/vidrieraDict.ts`. */
export const TEXTOS_VIDRIERA: Record<
  Locale,
  {
    aviso: string;
    verEjemplo: string;
    cerrada: string;
    inicio: string;
    /** Cierre de la carta de ejemplo: el original habla de lo que no cuesta. */
    ejemploNota: string;
    /** Arriba de los documentos legales, que describen el sitio vendiendo. */
    legal: string;
  }
> = {
  es: {
    aviso: "Sitio de muestra de dothecode: la compra y las cuentas están desactivadas.",
    verEjemplo: "Ver un informe de ejemplo",
    cerrada: "Esta página no está disponible en la versión de muestra.",
    inicio: "Ir al inicio",
    ejemploNota: "Fecha, hora y lugar de nacimiento. No hace falta cuenta y es gratis.",
    legal:
      "Este sitio es hoy una muestra de trabajo: no se puede comprar ni crear una cuenta, y los datos de nacimiento se usan en el momento para calcular la carta, sin guardarse. El documento que sigue describe el servicio tal como funcionó mientras se vendía, y se conserva como referencia.",
  },
  en: {
    aviso: "Showcase site by dothecode: purchases and accounts are turned off.",
    verEjemplo: "See a sample report",
    cerrada: "This page is not available in the showcase version.",
    inicio: "Go to the home page",
    ejemploNota: "Birth date, time and place. No account needed, and it is free.",
    legal:
      "This site is now a work showcase: you cannot buy anything or create an account, and birth details are used on the spot to calculate the chart, without being stored. The document below describes the service as it worked while it was on sale, and is kept for reference.",
  },
  pt: {
    aviso: "Site de demonstração da dothecode: a compra e as contas estão desativadas.",
    verEjemplo: "Ver um relatório de exemplo",
    cerrada: "Esta página não está disponível na versão de demonstração.",
    inicio: "Ir para o início",
    ejemploNota: "Data, hora e local de nascimento. Não precisa de conta e é grátis.",
    legal:
      "Este site é hoje uma demonstração de trabalho: não é possível comprar nem criar uma conta, e os dados de nascimento são usados na hora para calcular o mapa, sem serem guardados. O documento abaixo descreve o serviço como funcionou enquanto era vendido, e é mantido como referência.",
  },
};
