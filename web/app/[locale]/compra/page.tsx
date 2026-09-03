import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { CompraEspera } from "@/components/CompraEspera";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { getDict, isLocale } from "@/lib/i18n";
import { getSessionToken } from "@/lib/session";

// Adonde Stripe devuelve a quien terminó de pagar (`STRIPE_SUCCESS_URL`), con
// el `checkout_id` que Stripe reemplaza en la URL por `{CHECKOUT_SESSION_ID}`.
//
// No hay `generateStaticParams`: leer `searchParams` opta la página a
// renderizado dinámico, y además no hay nada que prerenderizar — lo único que
// muestra depende de una compra concreta.

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  // Nada de esto va al índice: es una pantalla de paso de una compra ajena.
  return { title: "ASTRA", robots: { index: false, follow: false } };
}

export default async function CompraPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  // Quien volvió de pagar en otro navegador no tiene sesión acá: que entre, y
  // lo comprado lo espera en su cuenta.
  if (!(await getSessionToken())) redirect(`/${locale}/entrar`);

  const dict = getDict(locale);
  const checkoutId = (await searchParams).checkout_id;

  return (
    <>
      <Nav locale={locale} dict={dict} path="/compra" signedIn />

      <main className="docFrame">
        {typeof checkoutId === "string" && checkoutId ? (
          <CompraEspera locale={locale} checkoutId={checkoutId} dict={dict} />
        ) : (
          // Sin `checkout_id` no hay compra que seguir: pasa si alguien entra a
          // mano o guardó el link. No es un error —puede haber pagado igual—,
          // así que se lo manda a donde está todo lo suyo.
          <section className="waiting">
            <div className="waitingCopy">
              <h1 className="display waitingTitle">{dict.compra.sinDatoTitle}</h1>
              <p className="waitingBody">{dict.compra.sinDatoBody}</p>
              <Link className="btn btnPrimary" href={`/${locale}/cuenta`}>
                {dict.compra.irACuenta}
              </Link>
            </div>
          </section>
        )}
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
