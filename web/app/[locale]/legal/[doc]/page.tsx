import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LegalDocument } from "@/components/LegalDocument";
import { Nav } from "@/components/Nav";
import { LEGAL, LEGAL_CONTACT, LEGAL_DOCS, LEGAL_UPDATED, type LegalDocKey } from "@/content/legal";
import { DEFAULT_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { Footer } from "@/components/Footer";
import { haySesion } from "@/lib/session";

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
      languages: {
        ...Object.fromEntries(LOCALES.map((code) => [code, `/${code}/legal/${doc}`])),
        "x-default": `/${DEFAULT_LOCALE}/legal/${doc}`,
      },
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

  // El header es el mismo en todo el sitio: sin esto la página se sirve
  // estática y le dice "Entrar" a alguien que ya tiene la sesión abierta.
  // Leer la cookie la vuelve dinámica, que es el precio de reconocer a quien
  // entra — y no toca lo que ve Google, que nunca trae cookie.
  const signedIn = await haySesion();

  return (
    <>
      <Nav
        locale={locale}
        dict={dict}
        path={`/legal/${doc}`}
        signedIn={signedIn}
        showExample={!signedIn}
      />
      <main className="docFrame">
        <LegalDocument
          doc={content[doc]}
          updatedLabel={content.updatedLabel}
          updated={LEGAL_UPDATED}
          contact={LEGAL_CONTACT}
        />
        <Footer locale={locale} dict={dict} />
      </main>
    </>
  );
}
