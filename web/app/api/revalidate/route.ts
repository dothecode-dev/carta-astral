import { timingSafeEqual } from "node:crypto";

import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";

import { LOCALES, NOTES_SLUG, isLocale } from "@/lib/i18n";

// Lo llama el CMS cuando una nota se publica o se despublica
// (`backend/cms/signals.py`). Sin esto la nota aparece igual, pero recién
// cuando vence el `revalidate = 300` de las páginas de notas: hasta cinco
// minutos entre apretar Publicar y verla. Con esto es inmediato.
//
// El secreto se compara en tiempo constante: comparar con `===` filtra, por lo
// que tarda, cuántos caracteres del principio coinciden — y este endpoint es
// público, así que se puede medir desde afuera.

export const dynamic = "force-dynamic";

const SECRETO = process.env.REVALIDATE_SECRET ?? "";

function coincide(recibido: string): boolean {
  // Sin secreto configurado no se revalida nada: fail-closed. Con la
  // comparación al revés, un despliegue sin la variable dejaría el endpoint
  // abierto a cualquiera que sepa la URL.
  if (!SECRETO) return false;
  const a = Buffer.from(recibido);
  const b = Buffer.from(SECRETO);
  // `timingSafeEqual` exige el mismo largo; compararlo antes ya filtra el
  // largo, que es información de bajo valor comparada con el contenido.
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  let cuerpo: { secret?: unknown; slug?: unknown; locale?: unknown };
  try {
    cuerpo = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  if (typeof cuerpo.secret !== "string" || !coincide(cuerpo.secret)) {
    // Sin detalle: quien no tiene el secreto tampoco tiene por qué saber si
    // falta la variable, si el largo estuvo cerca, ni si el slug existe.
    return NextResponse.json({ error: "no autorizado" }, { status: 401 });
  }

  const locale = typeof cuerpo.locale === "string" && isLocale(cuerpo.locale) ? cuerpo.locale : null;
  const slug = typeof cuerpo.slug === "string" ? cuerpo.slug : "";
  if (!locale || !slug) {
    return NextResponse.json({ error: "faltan locale o slug" }, { status: 400 });
  }

  // El listado y la nota, las dos: publicar una nota cambia las dos páginas, y
  // que la nota exista pero no figure en el índice es peor que la espera.
  const seccion = NOTES_SLUG[locale];
  const rutas = [`/${locale}/${seccion}`, `/${locale}/${seccion}/${slug}`];

  // El sitemap se arma con las notas publicadas, así que también queda viejo.
  // Va sin locale: es uno solo para todo el sitio.
  rutas.push("/sitemap.xml");

  for (const ruta of rutas) revalidatePath(ruta);

  return NextResponse.json({ revalidado: rutas });
}

// Un GET a mano es la forma más rápida de saber si la ruta existe en el
// despliegue, sin mandar el secreto por la barra del navegador.
export async function GET() {
  return NextResponse.json({
    ok: true,
    configurado: SECRETO !== "",
    idiomas: LOCALES,
  });
}
