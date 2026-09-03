import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ComprarBoton } from "@/components/ComprarBoton";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { fetchCatalogo, formatearPrecio, unidades } from "@/lib/catalogo";
import { DEFAULT_LOCALE, INTL_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
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
      languages: {
        ...Object.fromEntries(LOCALES.map((l) => [l, `${SITE_URL}/${l}/precios`])),
        // Declarar `languages` acá pisa entero el del layout, que sí lo traía:
        // sin esta línea la página quedaba sin `x-default` y a quien no le
        // calzaba ninguno de los tres idiomas Google le elegía uno por su
        // cuenta.
        "x-default": `${SITE_URL}/${DEFAULT_LOCALE}/precios`,
      },
    },
    // Sin esto la página heredaba el Open Graph del layout: compartir el link
    // de los precios mostraba el título de la home y `og:url` apuntando a la
    // home, o sea que el enlace previsualizaba —y llevaba— a otro lado.
    openGraph: {
      type: "website",
      siteName: "ASTRA",
      locale,
      title: `${dict.precios.title} · ASTRA`,
      description: dict.precios.lede,
      url: `${SITE_URL}/${locale}/precios`,
    },
    twitter: {
      card: "summary_large_image",
      title: `${dict.precios.title} · ASTRA`,
      description: dict.precios.lede,
    },
  };
}

export default async function PreciosPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const dict = getDict(locale);
  // En paralelo: la sesión decide si el botón compra o manda a entrar, y el
  // catálogo qué se muestra. Ninguna depende de la otra.
  const [productos, signedIn, query] = await Promise.all([
    fetchCatalogo(),
    haySesion(),
    searchParams,
  ]);
  // Lo que pidió comprar antes de que el login se interpusiera (lo puso
  // `ComprarBoton` al mandarlo a /entrar). Se contrasta contra el catálogo que
  // acaba de llegar: un código inventado en la URL no reanuda nada.
  const pedido =
    typeof query.comprar === "string" &&
    (productos ?? []).some((p) => p.codigo === query.comprar)
      ? query.comprar
      : null;

  // Cada producto como oferta, con su precio y su moneda: es de donde Google
  // saca el precio para mostrarlo en el resultado de búsqueda. Se arma del
  // mismo catálogo que pinta las tarjetas, así que no puede desincronizarse
  // de lo que se cobra. Sin catálogo no se declara nada —una oferta sin precio
  // es peor que ninguna—.
  const jsonLd = productos && {
    "@context": "https://schema.org",
    "@type": "ItemList",
    itemListElement: productos.map((producto, i) => ({
      "@type": "ListItem",
      position: i + 1,
      item: {
        "@type": "Product",
        name: dict.precios.nombre[producto.codigo] ?? producto.codigo,
        description: dict.precios.detalle[producto.codigo] ?? "",
        offers: {
          "@type": "Offer",
          price: (producto.precio_centavos / 100).toFixed(2),
          priceCurrency: producto.moneda.toUpperCase(),
          availability: "https://schema.org/InStock",
          url: `${SITE_URL}/${locale}/precios`,
        },
      },
    })),
  };

  return (
    <>
      <Nav locale={locale} dict={dict} path="/precios" signedIn={signedIn} />

      <main className="docFrame preciosFrame">
        <section className="preciosHead">
          <h1 className="display">{dict.precios.title}</h1>
          <p className="preciosLede">{dict.precios.lede}</p>
        </section>

        {/* Antes de todo lo que se cobra, y fuera de la grilla: no es un producto
            con su tarjeta, es el punto de partida. El catálogo público no la
            trae —vale cero—, así que sin escribirla acá la página decía que
            para probar ASTRA había que poner US$ 29, que es falso y es lo
            primero que ve quien llega de una búsqueda. */}
        <section className="preciosGratis">
          <div className="preciosGratisTexto">
            <h2 className="preciosGratisNombre">
              {dict.precios.gratisNombre} · <strong>{dict.precios.gratisPrecio}</strong>
            </h2>
            <p className="preciosGratisDetalle">{dict.precios.gratisDetalle}</p>
          </div>
          <Link className="btn btnGhost" href={`/${locale}/${signedIn ? "nueva" : "entrar"}`}>
            {dict.hero.cta}
          </Link>
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
              // El del medio: baja la unidad de US$ 29 a US$ 26,33 sin pedir
              // US$ 125 de una. Tres tarjetas iguales no ayudan a elegir, y
              // quien no sabe cuál mirar no elige ninguna.
              const recomendado = producto.codigo === "pack_3_natal";
              return (
                <li
                  key={producto.codigo}
                  className={`precioCard${recomendado ? " precioCardDestacado" : ""}`}
                >
                  {recomendado && <p className="precioDistintivo">{dict.precios.recomendado}</p>}
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
                    reanudar={pedido === producto.codigo}
                  />
                </li>
              );
            })}
          </ul>
        )}

        <p className="preciosNota">
          {dict.precios.nota}{" "}
          {/* Nadie compra 6.000 palabras a ciegas: acá está lo que se lee. */}
          <Link href={`/${locale}/ejemplo`}>{dict.precios.verEjemplo}</Link>
        </p>
      </main>

      <Footer locale={locale} dict={dict} />

      {jsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      )}
    </>
  );
}
