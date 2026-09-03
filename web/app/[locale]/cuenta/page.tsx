import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AccountCharts, type ChartSummary } from "@/components/AccountCharts";
import { DangerZone } from "@/components/DangerZone";
import { Compras } from "@/components/Compras";
import { Derechos } from "@/components/Derechos";
import { Nav } from "@/components/Nav";
import { SignOutButton } from "@/components/SignOutButton";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { ApiError, RUTA_SESION_EXPIRADA, callApi, getSessionToken } from "@/lib/session";
import { Footer } from "@/components/Footer";
import type { Derecho } from "@/lib/derechos";

type AccountResponse = {
  /** Con qué mail entró. Puede venir vacío: Apple deja ocultarlo. */
  email: string;
  derechos: Derecho[];
  deuda: number;
  account_id: number;
};

/** Lo que compró la cuenta, de la más nueva a la más vieja. */
type Compra = {
  codigo_producto: string;
  acreditada: boolean;
  created_at: string;
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
  let compras: Compra[];
  try {
    // En paralelo: son independientes y la pantalla necesita las dos.
    [account, charts, compras] = await Promise.all([
      callApi<AccountResponse>("/api/account/"),
      callApi<{ results: ChartSummary[] }>("/api/charts/").then((r) => r.results),
      callApi<{ compras: Compra[] }>("/api/compras/").then((r) => r.compras),
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
          <p className="accountEmail">
            {account.email
              ? dict.auth.conectadoComo.replace("{email}", account.email)
              : dict.auth.conectadoSinMail}
          </p>
          <Derechos derechos={account.derechos} dict={dict} locale={locale} />
        </section>

        <section className="accountSection">
          <p className="eyebrow">{dict.auth.comprasTitle}</p>
          <Compras compras={compras} locale={locale} dict={dict} />
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
