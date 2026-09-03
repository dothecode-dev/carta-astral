import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { SITE_URL } from "@/lib/config";
import { DEFAULT_LOCALE, NOTES_SLUG, getDict, isLocale, isNotesSection } from "@/lib/i18n";
import { fetchNote, fetchTranslationsOrNone, formatNoteDate } from "@/lib/notes";
import { haySesion } from "@/lib/session";

// Mismo criterio que el listado: sin `generateStaticParams`. Enumerar las notas
// en el build no sólo ata el build a que el CMS esté arriba —el CI no tiene
// backend—, sino que además deja fuera a cualquier nota publicada después, y el
// `dynamicParams = false` que el layout de `[locale]` declara para los idiomas
// las convertiría en 404 hasta el próximo deploy. Con `revalidate`, una nota
// nueva se genera en su primera visita y se sirve cacheada: es lo que sostiene
// el ritmo de publicar desde el CMS sin tocar el repo.
export const revalidate = 300;

type Params = { params: Promise<{ locale: string; section: string; slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { locale, section, slug } = await params;
  if (!isLocale(locale) || !isNotesSection(locale, section)) return {};
  const note = await fetchNote(locale, slug);
  if (!note) return {};

  // Las versiones publicadas en otros idiomas, para declararlas como la misma
  // nota traducida y no como artículos que compiten entre sí. Sólo las
  // publicadas: una traducción en borrador todavía daría 404.
  const traducciones = await fetchTranslationsOrNone(note.id);
  const languages: Record<string, string> = {
    [locale]: `/${locale}/${section}/${slug}`,
    ...Object.fromEntries(
      traducciones.map((t) => [t.locale, `/${t.locale}/${NOTES_SLUG[t.locale]}/${t.slug}`]),
    ),
  };

  return {
    metadataBase: new URL(SITE_URL),
    title: `${note.title} — ASTRA`,
    description: note.bajada,
    alternates: {
      canonical: `/${locale}/${section}/${slug}`,
      languages: {
        ...languages,
        // Al resto del mundo, la versión en el idioma por defecto si existe.
        "x-default": languages[DEFAULT_LOCALE] ?? languages[locale],
      },
    },
    openGraph: {
      type: "article",
      title: note.title,
      description: note.bajada,
      url: `/${locale}/${section}/${slug}`,
      publishedTime: note.fecha,
      ...(note.portada ? { images: [note.portada.url] } : {}),
    },
  };
}

export default async function NotePage({ params }: Params) {
  const { locale, section, slug } = await params;
  if (!isLocale(locale) || !isNotesSection(locale, section)) notFound();

  const note = await fetchNote(locale, slug);
  if (!note) notFound();

  const dict = getDict(locale);
  const fecha = formatNoteDate(locale, note.fecha);

  // El header es el mismo en todo el sitio: sin esto la página se sirve
  // estática y le dice "Entrar" a alguien que ya tiene la sesión abierta.
  // Leer la cookie la vuelve dinámica, que es el precio de reconocer a quien
  // entra — y no toca lo que ve Google, que nunca trae cookie.
  const signedIn = await haySesion();

  // Lo que Google usa para mostrar la nota como artículo en los resultados.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: note.title,
    description: note.bajada,
    datePublished: note.fecha,
    inLanguage: locale,
    author: { "@type": "Organization", name: "dothecode" },
    publisher: { "@type": "Organization", name: "ASTRA" },
    mainEntityOfPage: `${SITE_URL}/${locale}/${section}/${slug}`,
    ...(note.portada ? { image: note.portada.url } : {}),
  };

  return (
    <>
      {/* Al listado del otro idioma, no a esta misma nota: cada idioma tiene su
          propia nota con su propio slug, y puede no existir todavía. Mandarte a
          una URL que da 404 sería peor que dejarte en el listado. */}
      <Nav
        locale={locale}
        dict={dict}
        path={(code) => `/${NOTES_SLUG[code]}`}
        signedIn={signedIn}
        showExample={!signedIn}
      />

      <main className="docFrame">
        <article className="doc">
          <h1 className="display docTitle">{note.title}</h1>
          <p className="docMeta">
            {dict.notes.publishedOn} <time dateTime={note.fecha}>{fecha}</time>
          </p>

          {note.portada ? (
            // Sin `next/image` a propósito: el CMS ya devuelve la imagen
            // redimensionada (`portada_cabecera`, ancho 1600) con su ancho y su
            // alto, que es lo que hace falta para que no salte el layout.
            // Meter el optimizador en el medio pediría declarar el dominio del
            // backend en `next.config.ts` para no ganar nada.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className="noteCover"
              src={note.portada.url}
              width={note.portada.width}
              height={note.portada.height}
              alt={note.portada.alt}
            />
          ) : null}

          {/* El HTML lo produce el CMS, que sólo escriben editores con sesión
              en el admin de Wagtail, y `RichTextField` restringe las etiquetas
              a las declaradas en `features` (`cms/models.py`). */}
          <div className="noteBody" dangerouslySetInnerHTML={{ __html: note.cuerpo }} />

          <Link className="promiseLink" href={`/${locale}/${section}`}>
            {dict.notes.back}
          </Link>
        </article>
      </main>

      <Footer locale={locale} dict={dict} />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
    </>
  );
}
