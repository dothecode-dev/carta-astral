import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { GoogleSignIn } from "@/components/GoogleSignIn";
import { Nav } from "@/components/Nav";
import { destinoSeguro } from "@/lib/destino";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { sessionIsLive } from "@/lib/session";
import { Footer } from "@/components/Footer";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  return {
    title: `${getDict(locale).auth.title} — ASTRA`,
    // Una pantalla de acceso no aporta nada a una búsqueda.
    robots: { index: false, follow: true },
  };
}

/** El producto que se venía a comprar, si es que se venía a eso.
 *
 *  No se valida contra el catálogo acá —esta pantalla no lo tiene y pedirlo
 *  sólo para esto sería una llamada de red por login—: la forma alcanza para
 *  que no se pueda colar nada en la URL de destino, y /precios ignora un código
 *  que no exista. */
function productoPedido(comprar: unknown): string | null {
  return typeof comprar === "string" && /^[a-z0-9_]{1,40}$/.test(comprar) ? comprar : null;
}

export default async function SignInPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const query = await searchParams;
  const destino = destinoSeguro(query.next, locale);
  const producto = productoPedido(query.comprar);
  // La compra viaja aparte de la ruta: `destinoSeguro` rechaza cualquier `next`
  // con query justamente para no tener que razonar sobre lo que venga pegado.
  const volverA =
    destino && producto ? `${destino}?comprar=${encodeURIComponent(producto)}` : destino;

  // Quien ya entró no tiene nada que hacer acá. Se le pregunta al backend en
  // vez de confiar en que exista la cookie: una cookie que él ya no reconoce
  // mandaba a /cuenta, que rebotaba para acá, y así hasta la pantalla en blanco.
  if (await sessionIsLive()) redirect(volverA ?? `/${locale}/cuenta`);

  const dict = getDict(locale);

  return (
    <>
      <Nav locale={locale} dict={dict} path="/entrar" />

      <main className="docFrame authFrame">
        <section className="authCard">
          <h1 className="display authTitle">{dict.auth.title}</h1>
          <p className="authLede">{dict.auth.lede}</p>

          <GoogleSignIn
            locale={locale}
            next={volverA}
            labels={{
              loading: dict.auth.loading,
              blocked: dict.auth.blocked,
              failed: dict.auth.failed,
            }}
          />

          <p className="authLegal">
            {dict.auth.legal}{" "}
            <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
            {" · "}
            <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
          </p>
        </section>

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
