import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { Nav } from "@/components/Nav";
import { SignOutButton } from "@/components/SignOutButton";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { ApiError, callApi, getSessionToken } from "@/lib/session";

/** Lo que devuelve /api/account/: no hay email ni nombre. */
type AccountResponse = {
  credits_available: number;
  account_id: number;
};

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
  return { title: "ASTRA", robots: { index: false, follow: false } };
}

export default async function AccountPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  if (!(await getSessionToken())) redirect(`/${locale}/entrar`);

  const dict = getDict(locale);

  let account: AccountResponse;
  try {
    account = await callApi<AccountResponse>("/api/account/");
  } catch (error) {
    // Sesión vencida o cuenta borrada desde otro lado: se vuelve a entrar.
    if (error instanceof ApiError && error.status === 401) redirect(`/${locale}/entrar`);
    throw error;
  }

  return (
    <>
      <Nav locale={locale} dict={dict} path="/cuenta" signedIn />

      <main className="docFrame authFrame">
        <section className="authCard">
          <p className="eyebrow">{dict.auth.account}</p>
          <p className="balance">
            <span className="balanceGlyph" aria-hidden="true">
              ☉
            </span>
            <span className="balanceNumber">{account.credits_available}</span>
            <span className="balanceLabel">{dict.auth.credits}</span>
          </p>

          <SignOutButton locale={locale} label={dict.auth.signOut} />
        </section>
      </main>
    </>
  );
}
