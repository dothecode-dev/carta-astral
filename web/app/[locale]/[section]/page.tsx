import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { SITE_URL } from "@/lib/config";
import {
  DEFAULT_LOCALE,
  LOCALES,
  NOTES_SLUG,
  getDict,
  isLocale,
  isNotesSection,
} from "@/lib/i18n";
import { fetchNotes, formatNoteDate } from "@/lib/notes";
import { haySesion } from "@/lib/session";

// El segmento de la sección cambia con el idioma —`/es/notas`, `/en/notes`—
// porque la palabra en la URL es una señal de idioma para los buscadores.
// `isNotesSection` es lo que hace que exista sólo para el par correcto:
// `/en/notas` y `/es/cualquiera` son 404 antes de tocar el CMS.
//
// Deliberadamente sin `generateStaticParams`: prerenderizar el listado en el
// build lo ata a que el CMS esté arriba en ese momento, y el CI no tiene
// backend. Con `revalidate` la página se genera en la primera visita y se
// sirve cacheada, que es el mismo ISR que ya usa la portada.
export const revalidate = 300;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; section: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const dict = getDict(locale);
  return {
    metadataBase: new URL(SITE_URL),
    title: `${dict.notes.eyebrow} — ASTRA`,
    description: dict.notes.lede,
    alternates: {
      canonical: `/${locale}/${NOTES_SLUG[locale]}`,
      languages: {
        ...Object.fromEntries(LOCALES.map((code) => [code, `/${code}/${NOTES_SLUG[code]}`])),
        "x-default": `/${DEFAULT_LOCALE}/${NOTES_SLUG[DEFAULT_LOCALE]}`,
      },
    },
  };
}

export default async function NotesPage({
  params,
}: {
  params: Promise<{ locale: string; section: string }>;
}) {
  const { locale, section } = await params;
  if (!isLocale(locale) || !isNotesSection(locale, section)) notFound();

  const dict = getDict(locale);
  const notes = await fetchNotes(locale);

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
        path={(code) => `/${NOTES_SLUG[code]}`}
        signedIn={signedIn}
        showExample={!signedIn}
      />

      <div className="docFrame">
        <div className="sectionHead">
          <p className="eyebrow">{dict.notes.eyebrow}</p>
          <h1 className="display sectionTitle">{dict.notes.title}</h1>
          <p className="caption">{dict.notes.lede}</p>
        </div>

        {notes.length === 0 ? (
          <p className="caption">{dict.notes.empty}</p>
        ) : (
          <div className="notes">
            {notes.map((note) => (
              <Link className="note" href={`/${locale}/${section}/${note.slug}`} key={note.slug}>
                <span className="noteMeta">
                  <time dateTime={note.fecha}>{formatNoteDate(locale, note.fecha)}</time>
                </span>
                <span className="noteText">
                  <h2 className="noteTitle">{note.title}</h2>
                  <span className="noteBajada">{note.bajada}</span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
