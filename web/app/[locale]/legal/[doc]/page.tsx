import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LegalDocument } from "@/components/LegalDocument";
import { Nav } from "@/components/Nav";
import { LEGAL, LEGAL_CONTACT, LEGAL_DOCS, LEGAL_UPDATED, type LegalDocKey } from "@/content/legal";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://astra.dothecode.com";

function isDoc(value: string): value is LegalDocKey {
  return (LEGAL_DOCS as readonly string[]).includes(value);
}

export function generateStaticParams() {
  return LOCALES.flatMap((locale) => LEGAL_DOCS.map((doc) => ({ locale, doc })));
}

export const dynamicParams = false;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; doc: string }>;
}): Promise<Metadata> {
  const { locale, doc } = await params;
  if (!isLocale(locale) || !isDoc(doc)) return {};
  const content = LEGAL[locale][doc];
  return {
    metadataBase: new URL(SITE_URL),
    title: `${content.title} — ASTRA`,
    alternates: {
      canonical: `/${locale}/legal/${doc}`,
      languages: Object.fromEntries(LOCALES.map((code) => [code, `/${code}/legal/${doc}`])),
    },
    // Son documentos de referencia, no contenido por el que queramos posicionar.
    robots: { index: true, follow: true },
  };
}

export default async function LegalPage({
  params,
}: {
  params: Promise<{ locale: string; doc: string }>;
}) {
  const { locale, doc } = await params;
  if (!isLocale(locale) || !isDoc(doc)) notFound();

  const dict = getDict(locale);
  const content = LEGAL[locale];

  return (
    <>
      <Nav locale={locale} dict={dict} />
      <main className="docFrame">
        <LegalDocument
          doc={content[doc]}
          updatedLabel={content.updatedLabel}
          updated={LEGAL_UPDATED}
          contact={LEGAL_CONTACT}
        />

        <footer className="foot">
          <span>{dict.foot.brand}</span>
          <nav className="footLinks">
            <a href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</a>
            <a href={`/${locale}/legal/terms`}>{dict.foot.terms}</a>
            <a href={`mailto:${LEGAL_CONTACT}`}>{dict.foot.contact}</a>
          </nav>
        </footer>
      </main>
    </>
  );
}
