import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { VinculoPagina } from "@/components/VinculoPagina";
import { VINCULO } from "@/content/vinculo";
import { SYNASTRY_SLUG, getDict } from "@/lib/i18n";
import { haySesion } from "@/lib/session";
import { localeDelVinculo, vinculoActivo } from "@/lib/vinculo";
import { vinculoMetadata } from "@/lib/vinculoMetadata";

// Vínculo, fase 1: la vista previa pública de la sinastría, para medir cuánta
// gente llega y cuánta pide el informe antes de construir la compra. Las dos
// carpetas del slug traducido son copias de esta forma: ver
// `lib/vinculoMetadata.ts`. `pt` comparte la de `es`.
//
// Responde 404 mientras el backend no la encienda (`VINCULO_PREVIEW_ENABLED`):
// una landing que no puede confirmar el flag no se muestra.
const SLUG = "synastry";

// Siempre dinámica, a propósito. Sin esto la página es estática o dinámica según
// el flag de ESE momento: construida con el flag apagado, `notFound()` se lanza
// antes de `haySesion()` (que lee cookies) y la ruta queda prerenderizada como
// 404. Cuando se enciende el flag, cada regeneración llama a `cookies()` desde
// una ruta estática, falla con DYNAMIC_SERVER_USAGE y Next sigue sirviendo el
// 404 viejo: la landing no aparece NUNCA, y ningún test ni build lo muestra
// (se comprobó con un backend de mentira, el 05-10-2026). `vinculoActivo()`
// ya se cachea 5 minutos con `next.revalidate`: renderizar por pedido no suma
// llamadas al backend.
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return vinculoMetadata(locale, SLUG);
}

export default async function SynastryPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: segmento } = await params;
  const locale = localeDelVinculo(segmento, SLUG);
  if (!locale || !(await vinculoActivo())) notFound();

  const dict = getDict(locale);
  const t = VINCULO[locale];
  const signedIn = await haySesion();

  return (
    <>
      <Nav
        locale={locale}
        dict={dict}
        path={(code) => `/${SYNASTRY_SLUG[code]}`}
        signedIn={signedIn}
        showExample={!signedIn}
      />

      <main className="docFrame formFrame">
        <section className="formHead">
          <p className="eyebrow">{t.eyebrow}</p>
          <h1 className="display formTitle">{t.title}</h1>
          <p className="formLede">{t.intro}</p>
        </section>

        <VinculoPagina locale={locale} dict={dict} />
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
