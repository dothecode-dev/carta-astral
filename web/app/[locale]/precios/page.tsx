import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ComprarBoton } from "@/components/ComprarBoton";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { fetchCatalogo, formatearPrecio, unidades } from "@/lib/catalogo";
import { INTL_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { haySesion } from "@/lib/session";

// Los precios se ven SIN cuenta a propósito: quien llega de una publicación
// tiene que poder saber cuánto sale antes de que le pidan registrarse. Era el
// agujero de la navegación —el único lugar donde se podía comprar estaba dentro
// de una carta ya generada, y los packs no se podían comprar en ningún lado—.

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
  const dict = getDict(locale);
  return {
    title: `${dict.precios.title} · ASTRA`,
    description: dict.precios.lede,
    alternates: {
      canonical: `${SITE_URL}/${locale}/precios`,
      languages: Object.fromEntries(LOCALES.map((l) => [l, `${SITE_URL}/${l}/precios`])),
    },
  };
}

export default async function PreciosPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const dict = getDict(locale);
  // En paralelo: la sesión decide si el botón compra o manda a entrar, y el
  // catálogo qué se muestra. Ninguna depende de la otra.
  const [productos, signedIn] = await Promise.all([fetchCatalogo(), haySesion()]);

  return (
    <>
      <Nav locale={locale} dict={dict} path="/precios" signedIn={signedIn} />

      <main className="docFrame preciosFrame">
        <section className="preciosHead">
          <h1 className="display">{dict.precios.title}</h1>
          <p className="preciosLede">{dict.precios.lede}</p>
        </section>

        {productos === null ? (
          // El backend no respondió. Un aviso y la página en pie: mostrar
          // precios inventados sería peor que no mostrar ninguno.
          <p className="preciosVacio" role="alert">
            {dict.precios.sinCatalogo}
          </p>
        ) : (
          <ul className="preciosGrid">
            {productos.map((producto) => {
              const n = unidades(producto);
              const precio = formatearPrecio(
                producto.precio_centavos, producto.moneda, INTL_LOCALE[locale],
              );
              return (
                <li key={producto.codigo} className="precioCard">
                  <h2 className="precioNombre">
                    {dict.precios.nombre[producto.codigo] ?? producto.codigo}
                  </h2>
                  <p className="precioMonto">{precio}</p>
                  {n > 1 && (
                    // Lo que hace comparable un pack con el suelto: sin esto,
                    // "US$ 125" al lado de "US$ 29" parece más caro.
                    <p className="precioUnidad">
                      {dict.precios.porUnidad.replace(
                        "{precio}",
                        formatearPrecio(
                          Math.round(producto.precio_centavos / n),
                          producto.moneda,
                          INTL_LOCALE[locale],
                        ),
                      )}
                    </p>
                  )}
                  <p className="precioDetalle">
                    {dict.precios.detalle[producto.codigo] ?? ""}
                  </p>
                  <ComprarBoton
                    codigo={producto.codigo}
                    locale={locale}
                    dict={dict}
                    signedIn={signedIn}
                  />
                </li>
              );
            })}
          </ul>
        )}

        <p className="preciosNota">{dict.precios.nota}</p>
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
