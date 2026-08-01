import { notFound } from "next/navigation";

import { EphemerisRail } from "@/components/EphemerisRail";
import { LEGAL_CONTACT } from "@/content/legal";
import { Nav } from "@/components/Nav";
import { SkyWheel } from "@/components/SkyWheel";
import { getDict, isLocale } from "@/lib/i18n";
import { fetchSky } from "@/lib/sky";

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

          <section>
            <div className="sectionHead">
              <p className="eyebrow">{dict.notes.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.notes.title}</h2>
            </div>

            <div className="notes">
              {dict.notes.items.map((note) => (
                <a className="note" href="#" key={note.title}>
                  <span className="noteMeta">{note.meta}</span>
                  <h3 className="noteTitle">{note.title}</h3>
                  <span className="noteSign" aria-hidden="true">
                    {note.sign}
                  </span>
                </a>
              ))}
            </div>
          </section>

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
              <p className="eyebrow">{dict.credits.eyebrow}</p>
              <h2 className="display sectionTitle">{dict.credits.title}</h2>
            </div>

            <table className="packsTable">
              <thead>
                <tr>
                  <th>{dict.credits.colCredits}</th>
                  <th>{dict.credits.colPrice}</th>
                  <th>{dict.credits.colUnit}</th>
                </tr>
              </thead>
              <tbody>
                {dict.credits.packs.map((pack) => (
                  <tr
                    key={pack.credits}
                    className={pack.popular ? "packPopular" : undefined}
                  >
                    <th scope="row">
                      {pack.credits}
                      {pack.popular ? (
                        <span className="tag">{dict.credits.popular}</span>
                      ) : null}
                    </th>
                    <td>{pack.price}</td>
                    <td className="unit">{pack.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <table className="termsTable">
              <tbody>
                {dict.credits.terms.map((term) => (
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
              {dict.credits.note}
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

            <div className="stores">
              {/* Badges propios: los oficiales de Apple y Google tienen guías de
                  marca obligatorias y hay que reemplazarlos antes de publicar. */}
              <a className="store" href="#">
                <svg
                  width="17"
                  height="21"
                  viewBox="0 0 17 21"
                  aria-hidden="true"
                >
                  <path
                    fill="currentColor"
                    d="M14.09 11.02c-.02-2.2 1.8-3.36 1.88-3.42-1.02-1.5-2.62-1.7-3.18-1.72-1.35-.14-2.64.8-3.33.8-.69 0-1.75-.78-2.87-.76-1.48.02-2.84.86-3.6 2.18-1.53 2.66-.39 6.6 1.1 8.76.73 1.06 1.6 2.25 2.74 2.2 1.1-.04 1.51-.71 2.84-.71 1.33 0 1.7.71 2.86.69 1.18-.02 1.93-1.08 2.65-2.14.83-1.22 1.18-2.4 1.2-2.47-.03-.01-2.29-.88-2.31-3.49z"
                  />
                  <path
                    fill="currentColor"
                    d="M11.9 4.48c.61-.74 1.02-1.77.91-2.79-.88.04-1.94.58-2.57 1.32-.56.65-1.05 1.7-.92 2.7.98.08 1.98-.5 2.58-1.23z"
                  />
                </svg>
                <span className="storeText">
                  <span className="storeSmall">{dict.download.appleSmall}</span>
                  <span className="storeName">App Store</span>
                </span>
              </a>

              <a className="store" href="#">
                <svg
                  width="19"
                  height="21"
                  viewBox="0 0 19 21"
                  aria-hidden="true"
                >
                  <path
                    fill="currentColor"
                    d="M1.1 1.2C.9 1.5.8 1.9.8 2.5v16c0 .6.1 1 .3 1.3l8.4-8.8L1.1 1.2z"
                  />
                  <path
                    fill="currentColor"
                    d="M10.6 10.1l2.7-2.8L2.9.6C2.4.3 1.9.2 1.5.4l9.1 9.7z"
                  />
                  <path
                    fill="currentColor"
                    d="M10.6 11.9L1.5 20.6c.4.2.9.1 1.4-.2l10.4-6.7-2.7-1.8z"
                  />
                  <path
                    fill="currentColor"
                    d="M17.4 9.2l-2.9-1.9-3 3.2 3 3.1 2.9-1.9c.9-.6.9-1.9 0-2.5z"
                  />
                </svg>
                <span className="storeText">
                  <span className="storeSmall">{dict.download.playSmall}</span>
                  <span className="storeName">Google Play</span>
                </span>
              </a>
            </div>
          </section>

          <footer className="foot">
            <span>{dict.foot.brand}</span>
            <nav className="footLinks">
              <a href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</a>
              <a href={`/${locale}/legal/terms`}>{dict.foot.terms}</a>
              <a href={`mailto:${LEGAL_CONTACT}`}>{dict.foot.contact}</a>
            </nav>
          </footer>
        </main>
      </div>
    </>
  );
}
