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

/** Los textos propios del modo. Acá y no en el diccionario: son tres frases
 *  que sólo existen en la vidriera. */
export const TEXTOS_VIDRIERA: Record<Locale, { aviso: string; verEjemplo: string; cerrada: string; inicio: string }> = {
  es: {
    aviso: "Sitio de muestra de dothecode: la compra y las cuentas están desactivadas.",
    verEjemplo: "Ver un informe de ejemplo",
    cerrada: "Esta página no está disponible en la versión de muestra.",
    inicio: "Ir al inicio",
  },
  en: {
    aviso: "Showcase site by dothecode: purchases and accounts are turned off.",
    verEjemplo: "See a sample report",
    cerrada: "This page is not available in the showcase version.",
    inicio: "Go to the home page",
  },
  pt: {
    aviso: "Site de demonstração da dothecode: a compra e as contas estão desativadas.",
    verEjemplo: "Ver um relatório de exemplo",
    cerrada: "Esta página não está disponível na versão de demonstração.",
    inicio: "Ir para o início",
  },
};
