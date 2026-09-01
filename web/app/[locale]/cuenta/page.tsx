import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AccountCharts, type ChartSummary } from "@/components/AccountCharts";
import { DangerZone } from "@/components/DangerZone";
import { Nav } from "@/components/Nav";
import { SignOutButton } from "@/components/SignOutButton";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { ApiError, RUTA_SESION_EXPIRADA, callApi, getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";
import { cantidad, type Derecho } from "@/lib/derechos";

/** Lo que devuelve /api/account/: no hay email ni nombre. */
type AccountResponse = {
  derechos: Derecho[];
  deuda: number;
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
    // Sesión vencida o cuenta borrada desde otro lado: se vuelve a entrar, pero
    // pasando por la ruta que borra la cookie muerta. Mandarlo derecho a
    // /entrar dejaría la cookie viva y el navegador rebotaría entre las dos.
    if (error instanceof ApiError && error.status === 401) redirect(RUTA_SESION_EXPIRADA(locale));
    throw error;
  }

  return (
    <>
      <Nav locale={locale} dict={dict} path="/cuenta" signedIn showExample={charts.length === 0} />

      <main className="docFrame accountFrame">
        <section className="accountHead">
          <p className="eyebrow">{dict.auth.account}</p>
          <div className="balanceRow">
            <div className="balances">
              <p className="balance">
                <span className="balanceGlyph" aria-hidden="true">
                  ☉
                </span>
                <span className="balanceNumber">{cantidad(account.derechos, "lectura_breve")}</span>
                <span className="balanceLabel">{dict.auth.freeCredits}</span>
              </p>
              <p className="balance">
                <span className="balanceGlyph" aria-hidden="true">
                  ☾
                </span>
                <span className="balanceNumber">{cantidad(account.derechos, "informe_natal")}</span>
                <span className="balanceLabel">{dict.auth.paidCredits}</span>
              </p>
            </div>
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

        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
