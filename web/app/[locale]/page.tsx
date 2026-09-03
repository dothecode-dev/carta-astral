import Link from "next/link";
import { notFound } from "next/navigation";

import { EphemerisRail } from "@/components/EphemerisRail";
import { Nav } from "@/components/Nav";
import { SkyWheel } from "@/components/SkyWheel";
import { NOTES_SLUG, getDict, isLocale } from "@/lib/i18n";
import { fetchNotesOrNone, formatNoteDate } from "@/lib/notes";
import { fetchSky } from "@/lib/sky";
import { SITE_URL } from "@/lib/config";
import { Footer } from "@/components/Footer";
import { haySesion } from "@/lib/session";

export default async function Home({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const dict = getDict(locale);
  // Del backend, con Swiss Ephemeris. Si no contesta, la rueda se calcula en
  // el navegador y la portada no se entera.
  const sky = await fetchSky();
  const notes = await fetchNotesOrNone(locale, 3);

  // El header es el mismo en todo el sitio: sin esto la página se sirve
  // estática y le dice "Entrar" a alguien que ya tiene la sesión abierta.
  // Leer la cookie la vuelve dinámica, que es el precio de reconocer a quien
  // entra — y no toca lo que ve Google, que nunca trae cookie.
  const signedIn = await haySesion();

  // Lo que le dice a Google qué es este sitio y quién lo hace. Sin esto,
  // `Article` en las notas era el único dato estructurado del dominio: la
  // portada, que es la que se busca por marca, no declaraba nada.
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organizacion`,
        name: "ASTRA",
        url: SITE_URL,
        founder: { "@type": "Organization", name: "dothecode" },
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#sitio`,
        name: "ASTRA",
        url: `${SITE_URL}/${locale}`,
        inLanguage: locale,
        description: dict.meta.description,
        publisher: { "@id": `${SITE_URL}/#organizacion` },
      },
    ],
  };

  return (
    <>
      <Nav locale={locale} dict={dict} signedIn={signedIn} showExample={!signedIn} />

      <div className="frame">
        <EphemerisRail
          locale={locale}
          eyebrow={dict.rail.eyebrow}
          note={dict.rail.note}
          initial={sky?.positions ?? null}
        />

        <main className="main">
          <section className="hero">
            <SkyWheel
              alt={dict.hero.wheelAlt}
              initial={sky?.positions ?? null}
            />

            <div className="heroCopy">
              <h1 className="display heroTitle">{dict.hero.title}</h1>
              <p className="heroLede">
                {dict.hero.lede} <strong>{dict.hero.ledeStrong}</strong>
              </p>
              <div className="actions">
                <a className="btn btnPrimary" href={`/${locale}/nueva`}>
                  {dict.hero.cta}
                </a>
                <a className="btn btnGhost" href={`/${locale}/ejemplo`}>
                  {dict.hero.ctaSecondary}
                </a>
              </div>
            </div>
          </section>

          <section>
            <div className="sectionHead">
              <p className="eyebrow">{dict.flow.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.flow.title}</h2>
            </div>

            <div className="flow">
              {dict.flow.steps.map((step) => (
                <article className="step" key={step.title}>
                  <p className="eyebrow">{step.label}</p>
                  <h3 className="stepTitle">{step.title}</h3>
                  <p className="stepBody">{step.body}</p>
                </article>
              ))}
            </div>
          </section>

          {/* Las tres últimas notas publicadas. Si el idioma todavía no tiene
              ninguna —o el CMS no contesta— la sección no se muestra: es lo
              que antes se resolvía con tres artículos inventados. */}
          {notes.length > 0 && (
            <section>
              <div className="sectionHead">
                <p className="eyebrow">{dict.notes.eyebrow}</p>
                <h2 className="display sectionTitle">{dict.notes.title}</h2>
              </div>

              <div className="notes">
                {notes.map((note) => (
                  <Link
                    className="note"
                    href={`/${locale}/${NOTES_SLUG[locale]}/${note.slug}`}
                    key={note.slug}
                  >
                    <span className="noteMeta">
                      <time dateTime={note.fecha}>{formatNoteDate(locale, note.fecha, "short")}</time>
                    </span>
                    <span className="noteText">
                      <h3 className="noteTitle">{note.title}</h3>
                      <span className="noteBajada">{note.bajada}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          <section>
            <div className="sectionHead">
              <p className="eyebrow">{dict.privacy.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.privacy.title}</h2>
            </div>

            <div className="promise">
              <ul className="promiseList">
                {dict.privacy.points.map((point) => (
                  <li key={point.strong}>
                    <span className="promiseMark" aria-hidden="true">
                      —
                    </span>
                    <span>
                      <b>{point.strong}</b> {point.rest}
                    </span>
                  </li>
                ))}
              </ul>
              <a className="promiseLink" href={`/${locale}/legal/privacy`}>
                {dict.privacy.link}
              </a>
            </div>
          </section>

          <section>
            <div className="sectionHead">
              <p className="eyebrow">{dict.pricing.eyebrow}</p>
              <h2 className="display sectionTitle pricingTitle">{dict.pricing.title}</h2>
            </div>

            <p className="priceTag">
              <span className="priceAmount">{dict.pricing.price}</span>
              <span className="priceLabel">{dict.pricing.priceNote}</span>
            </p>

            <table className="termsTable">
              <tbody>
                {dict.pricing.terms.map((term) => (
                  <tr key={term.label}>
                    <th scope="row">{term.label}</th>
                    <td className={term.free ? "free" : undefined}>
                      {term.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="caption" style={{ marginTop: "1.25rem" }}>
              {dict.pricing.note}
            </p>

            {/* La sección terminaba en la nota, sin un solo enlace: la tabla
                decía cuánto sale y no había por dónde seguir. Los packs, que
                son lo de mejor margen, no se nombraban en ningún lado de la
                home. */}
            <p className="pricingCta">
              <Link className="btn btnGhost" href={`/${locale}/precios`}>
                {dict.pricing.cta}
              </Link>
            </p>
          </section>

          <section>
            <div className="sectionHead">
              <p className="eyebrow">{dict.faq.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.faq.title}</h2>
            </div>

            <div className="faq">
              {dict.faq.items.map((item) => (
                <div className="faqItem" key={item.q}>
                  <h3 className="faqQ">{item.q}</h3>
                  <p className="faqA">{item.a}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="cierre">
            <div className="sectionHead">
              <p className="eyebrow">{dict.cierre.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.cierre.title}</h2>
              <p className="caption">{dict.cierre.note}</p>
            </div>

            <div className="actions">
              <a className="btn btnPrimary" href={`/${locale}/nueva`}>
                {dict.cierre.cta}
              </a>
            </div>
          </section>
          <Footer locale={locale} dict={dict} />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
        </main>
      </div>
    </>
  );
}
