import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AccountCharts, type ChartSummary } from "@/components/AccountCharts";
import { DangerZone } from "@/components/DangerZone";
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
  let charts: ChartSummary[];
  try {
    // En paralelo: son independientes y la pantalla necesita las dos.
    [account, charts] = await Promise.all([
      callApi<AccountResponse>("/api/account/"),
      callApi<{ results: ChartSummary[] }>("/api/charts/").then((r) => r.results),
    ]);
  } catch (error) {
    // Sesión vencida o cuenta borrada desde otro lado: se vuelve a entrar.
    if (error instanceof ApiError && error.status === 401) redirect(`/${locale}/entrar`);
    throw error;
  }

  return (
    <>
      <Nav locale={locale} dict={dict} path="/cuenta" signedIn />

      <main className="docFrame accountFrame">
        <section className="accountHead">
          <p className="eyebrow">{dict.auth.account}</p>
          <div className="balanceRow">
            <p className="balance">
              <span className="balanceGlyph" aria-hidden="true">
                ☉
              </span>
              <span className="balanceNumber">{account.credits_available}</span>
              <span className="balanceLabel">{dict.auth.credits}</span>
            </p>
            <div className="buyBlock">
              <button type="button" className="btn btnGhost" disabled>
                {dict.auth.buyCredits}
              </button>
              <p className="buyNote">{dict.auth.buyInApp}</p>
            </div>
          </div>
        </section>

        <section className="accountSection">
          <p className="eyebrow">{dict.auth.chartsTitle}</p>
          <AccountCharts charts={charts} locale={locale} dict={dict} />
        </section>

        <section className="accountSection">
          <p className="eyebrow">{dict.auth.settings}</p>
          <nav className="accountLinks">
            <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
            <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
          </nav>
        </section>

        <DangerZone locale={locale} dict={dict} />

        <div className="accountFoot">
          <SignOutButton locale={locale} label={dict.auth.signOut} />
        </div>
      </main>
    </>
  );
}
