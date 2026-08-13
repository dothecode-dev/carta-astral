// Las dos direcciones que necesita el sitio, resueltas en un solo lugar.
//
// Ojo con el string vacío: en el Dockerfile, `ENV VAR=$ARG` con el argumento
// sin pasar deja la variable definida y vacía, no ausente. Con `??` eso no cae
// al valor por defecto —sólo lo hace con undefined— y `new URL("")` rompe el
// build entero. Es exactamente lo que tiró abajo el deploy del 2026-08-02.

function envOr(value: string | undefined, fallback: string): string {
  return value && value.trim() ? value.trim() : fallback;
}

/** Origen público del sitio: canonical, hreflang, sitemap y Open Graph.
 *
 * El fallback tiene que ser el dominio real de producción. Con el dominio viejo
 * acá, un deploy sin la variable no rompe nada visible: el sitio levanta bien y
 * sirve canonical y hreflang apuntando a un dominio ajeno, que es la forma más
 * rápida de que Google desindexe el sitio sin que nadie se entere. */
export const SITE_URL = envOr(process.env.NEXT_PUBLIC_SITE_URL, "https://astraguia.com");

/** Backend. Se lee sólo desde el servidor, nunca desde el navegador. */
export const API_URL = envOr(process.env.API_URL, "https://api.cartaastral.dothecode.com");
