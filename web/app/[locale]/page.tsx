import Link from "next/link";
import { notFound } from "next/navigation";

import { EphemerisRail } from "@/components/EphemerisRail";
import { Nav } from "@/components/Nav";
import { SkyWheel } from "@/components/SkyWheel";
import { NOTES_SLUG, getDict, isLocale } from "@/lib/i18n";
import { fetchNotesOrNone, formatNoteDate } from "@/lib/notes";
import { fetchSky } from "@/lib/sky";
import { StoreBadges } from "@/components/StoreBadges";
import { Footer } from "@/components/Footer";

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

  return (
    <>
      <Nav locale={locale} dict={dict} />

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
                <a className="btn btnPrimary" href="#descargar">
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

          <section className="download" id="descargar">
            <div className="sectionHead">
              <p className="eyebrow">{dict.download.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.download.title}</h2>
              <p className="caption">{dict.download.note}</p>
            </div>

            <StoreBadges dict={dict} />
          </section>
          <Footer locale={locale} dict={dict} />
        </main>
      </div>
    </>
  );
}
