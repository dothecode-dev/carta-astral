import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { GoogleSignIn } from "@/components/GoogleSignIn";
import { Nav } from "@/components/Nav";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { getSessionToken } from "@/lib/session";

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

export default async function SignInPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  // Quien ya entró no tiene nada que hacer acá.
  if (await getSessionToken()) redirect(`/${locale}/cuenta`);

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
      </main>
    </>
  );
}
