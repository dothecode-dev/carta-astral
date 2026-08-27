import { type NextRequest, NextResponse } from "next/server";

/** El proxy de PostHog, servido desde nuestro propio dominio.
 *
 * Existe porque los bloqueadores de publicidad filtran por dominio y se comen
 * una parte grande de las visitas si el navegador llama a posthog.com directo.
 * La ruta se llama `/rueda` y no `/analytics`, `/tracking` o `/ingest`: esos
 * nombres también están en las listas.
 *
 * **No se hace con `rewrites` de Next, y la razón es de seguridad.** Un rewrite
 * a un host externo reenvía las cabeceras de entrada tal cual, `Cookie`
 * incluida — está medido: apuntando el rewrite a un servidor local, el destino
 * recibió `astra_session=...`. Y esa cookie no es de analítica: lleva el token
 * bearer del backend (`lib/session.ts`, `app/api/session/route.ts`), que vale
 * 90 días y da acceso completo a la cuenta. Con PostHog del otro lado, ese
 * token habría quedado en los logs de ingesta de un tercero.
 *
 * Acá el pedido de salida se arma desde cero: viajan el cuerpo y el tipo de
 * contenido, nada más. Ni `Cookie`, ni `Authorization`, ni nada que el
 * navegador agregue por ser same-origin.
 */

const INGESTA = "https://us.i.posthog.com";
const ASSETS = "https://us-assets.i.posthog.com";

/** Sin esto Next intentaría tratar de estática una ruta que es un túnel. */
export const dynamic = "force-dynamic";

function destino(segmentos: string[], pathname: string, search: string): string {
  // El primer segmento decide el host: los scripts del SDK viven en el CDN de
  // assets y los eventos en el de ingesta.
  const base = segmentos[0] === "static" || segmentos[0] === "array" ? ASSETS : INGESTA;
  // Se usa el pathname original y no los segmentos para conservar la barra
  // final: la API de PostHog la usa (`/e/`) y sin ella responde distinto.
  return base + pathname.replace(/^\/rueda/, "") + search;
}

async function reenviar(req: NextRequest, segmentos: string[]): Promise<NextResponse> {
  const url = destino(segmentos, req.nextUrl.pathname, req.nextUrl.search);

  const cabeceras = new Headers();
  const tipo = req.headers.get("content-type");
  if (tipo) cabeceras.set("content-type", tipo);
  // La IP real del visitante, que es lo que PostHog usa para deducir el país.
  // Sin esto todos los eventos parecerían venir del servidor. Es lo único de la
  // request original que se reenvía además del cuerpo, y la política de
  // privacidad lo declara: se usa para el país y no se almacena.
  const ip = req.headers.get("x-forwarded-for");
  if (ip) cabeceras.set("x-forwarded-for", ip);

  let respuesta: Response;
  try {
    respuesta = await fetch(url, {
      method: req.method,
      headers: cabeceras,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      // Un redirect del upstream se sigue acá, no en el navegador.
      redirect: "follow",
    });
  } catch (error) {
    // Que la analítica esté caída no puede tumbar la página que mide, pero
    // tampoco se traga en silencio: sin log, un corte de PostHog se vería como
    // "no entra nadie" en vez de como lo que es.
    console.error("[rueda] falló el reenvío a PostHog", { url, error });
    return new NextResponse(null, { status: 502 });
  }

  const salida = new Headers();
  for (const clave of ["content-type", "content-encoding", "cache-control", "etag"]) {
    const valor = respuesta.headers.get(clave);
    if (valor) salida.set(clave, valor);
  }

  return new NextResponse(respuesta.body, { status: respuesta.status, headers: salida });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return reenviar(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return reenviar(req, (await ctx.params).path);
}

export async function OPTIONS(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return reenviar(req, (await ctx.params).path);
}
