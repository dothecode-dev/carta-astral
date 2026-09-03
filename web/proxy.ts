import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { API_URL } from "@/lib/config";
import { DEFAULT_LOCALE, LOCALES, negociarIdioma, type Locale } from "@/lib/i18n";

// El cartel de mantenimiento, para desplegar sin cortar un informe por la mitad.
//
// En Next 16 esto se llama `proxy.ts` y no `middleware.ts` (ver
// `node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md`): mismo
// mecanismo, otro nombre.
//
// Responde acá y no en una página porque así el cartel sale con 503 —un 200
// diciendo "ya volvemos" es una página que Google puede indexar— y porque no
// depende de que el resto de la app renderice: si el mantenimiento se prendió
// justamente porque algo está roto, este HTML igual se muestra.
//
// La doc advierte que el proxy no es lugar para traer datos lentos, y tiene
// razón: por eso la consulta al backend se cachea en memoria unos segundos y
// una petición fallida se toma como "abierto".

/** Cuánto vale el estado antes de volver a preguntar. */
const TTL_MS = 5000;
/** Un backend que no contesta no puede cerrar el sitio: la consulta se corta. */
const TIMEOUT_MS = 1500;

let cache: { valor: boolean; hasta: number } | null = null;

async function enMantenimiento(): Promise<boolean> {
  const ahora = Date.now();
  if (cache && cache.hasta > ahora) return cache.valor;

  let valor = false;
  try {
    const res = await fetch(`${API_URL}/api/estado/`, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
      // `cache` y `next.revalidate` no tienen efecto acá (lo dice la doc del
      // proxy): el caché es el de arriba, a mano.
      cache: "no-store",
    });
    if (res.ok) valor = ((await res.json()) as { mantenimiento?: boolean }).mantenimiento === true;
  } catch {
    // Sin respuesta se sigue de largo. Fallar al revés —cerrar el sitio porque
    // una consulta falló— convertiría un hipo del backend en una caída total.
  }
  cache = { valor, hasta: ahora + TTL_MS };
  return valor;
}

function idiomaDe(pathname: string): Locale {
  const primero = pathname.split("/")[1];
  return (LOCALES as readonly string[]).includes(primero) ? (primero as Locale) : DEFAULT_LOCALE;
}

const CARTEL: Record<Locale, { title: string; body: string }> = {
  es: {
    title: "Estamos aceitando el universo",
    body: "Danos cinco minutos y volvé a intentar.",
  },
  en: {
    title: "We're oiling the universe",
    body: "Give us five minutes and try again.",
  },
  pt: {
    title: "Estamos lubrificando o universo",
    body: "Nos dê cinco minutos e tente de novo.",
  },
};

/** El cartel, autocontenido: sin fuentes ni CSS de la app, que pueden no estar. */
function pagina(locale: Locale): string {
  const { title, body } = CARTEL[locale];
  return `<!doctype html><html lang="${locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>ASTRA</title>
<style>
  :root { color-scheme: dark }
  body { margin:0; min-height:100dvh; display:grid; place-items:center; text-align:center;
         background:#1a0f1f; color:#f3ebe4; padding:2rem;
         font-family: ui-sans-serif, system-ui, -apple-system, sans-serif }
  h1 { font-family: Georgia, "Times New Roman", serif; font-weight:300;
       font-size: clamp(1.75rem, 5vw, 2.75rem); margin:0 0 .75rem; letter-spacing:-.01em }
  p { margin:0; color:#c9b8c4; font-size:1.0625rem }
</style></head>
<body><main><h1>${title}</h1><p>${body}</p></main></body></html>`;
}

export async function proxy(request: NextRequest) {
  if (!(await enMantenimiento())) {
    // La raíz no tiene página propia: manda al idioma que pide el navegador.
    // Estaba en `redirects()` de `next.config.ts` con destino fijo a `/es`, y
    // ahí no servía —un redirect estático no puede mirar una cabecera—, así que
    // un brasileño que entraba por astraguia.com veía todo en español.
    //
    // La URL sale de `nextUrl.clone()` y NO de `new URL(path, request.url)`:
    // detrás de Traefik, `request.url` es la del contenedor y el Location
    // saldría apuntando a `https://0.0.0.0:3000/...`. Ya pasó en `/entrar`.
    // Un Location relativo tampoco sirve acá —el proxy lo parsea como URL y
    // tira `ERR_INVALID_URL`—, aunque sí funcione en un Route Handler.
    if (request.nextUrl.pathname === "/") {
      const destino = new URL(request.nextUrl);
      destino.pathname = `/${negociarIdioma(request.headers.get("accept-language"))}`;
      const res = NextResponse.redirect(destino, 307);
      // Que el CDN no le sirva a todo el mundo el idioma del primero que pasó.
      res.headers.set("Vary", "Accept-Language");
      return res;
    }
    return NextResponse.next();
  }

  return new NextResponse(pagina(idiomaDe(request.nextUrl.pathname)), {
    status: 503,
    headers: {
      "content-type": "text/html; charset=utf-8",
      // Que nadie —ni un CDN ni el navegador— se guarde este cartel: cuando el
      // deploy termina, la página siguiente tiene que ser la de verdad.
      "cache-control": "no-store",
      // Minutos, no horas: es lo que un cliente educado hace con un 503.
      "retry-after": "300",
    },
  });
}

export const config = {
  // Las páginas sí; los assets y las rutas internas no. Esas últimas sostienen
  // el sondeo de quien está esperando un informe ya empezado, y cortarlas sería
  // romper justamente lo que el mantenimiento existe para cuidar.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|fonts|.*\\.(?:png|jpg|jpeg|svg|webp|ico|txt|xml)$).*)"],
};
