import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { CanjeCompra } from "@/components/CanjeCompra";
import { CompraEspera } from "@/components/CompraEspera";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { nombre } from "@/lib/compraCookie";
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

  // Los dos nombres: la variable `STRIPE_SUCCESS_URL` la escribe una persona
  // en el panel de deploy, y la documentación de Stripe usa `session_id` en
  // todos sus ejemplos. El 04-09-2026 el staging tenía justamente ese, y quien
  // terminaba de pagar caía en la pantalla genérica en vez de ver su informe
  // escribiéndose. Aceptar los dos cuesta una línea; que dependa de que nadie
  // copie el ejemplo de Stripe, una compra.
  const sp = await searchParams;
  const checkoutId = sp.checkout_id ?? sp.session_id;

  // Primero la cookie del nonce de ESTE checkout (RF14): si está, este
  // navegador es el que abrió un pago sin cuenta, y el canje decide —con o sin
  // sesión, y aunque la sesión abierta sea de otra cuenta: la compra es de
  // quien pagó—. Se mira sólo si existe; el valor lo lee la ruta del canje,
  // nunca esta página.
  const cookieCompra = nombre(checkoutId);
  if (cookieCompra && typeof checkoutId === "string" && (await cookies()).has(cookieCompra)) {
    const dict = getDict(locale);
    const signedIn = (await getSessionToken()) !== null;
    return (
      <>
        <Nav locale={locale} dict={dict} path="/compra" signedIn={signedIn} />
        <main className="docFrame">
          <CanjeCompra locale={locale} checkoutId={checkoutId} dict={dict} />
        </main>
        <Footer locale={locale} dict={dict} />
      </>
    );
  }

  // Quien volvió de pagar en otro navegador no tiene sesión acá: que entre, y
  // lo comprado lo espera en su cuenta.
  if (!(await getSessionToken())) redirect(`/${locale}/entrar`);

  const dict = getDict(locale);

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
