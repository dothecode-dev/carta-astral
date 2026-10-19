import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ComprarBoton } from "@/components/ComprarBoton";
import { CuponInput } from "@/components/CuponInput";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { fetchCatalogo, formatearPrecio, precioEn, unidades } from "@/lib/catalogo";
import { fetchCupon, normalizarCupon } from "@/lib/cupon";
import { DEFAULT_LOCALE, INTL_LOCALE, LOCALES, getDict, isLocale } from "@/lib/i18n";
import { SITE_URL } from "@/lib/config";
import { MONEDAS, monedaDelVisitante, monedaPara, monedasOfrecidas } from "@/lib/moneda";
import { callApi, haySesion } from "@/lib/session";
import type { ChartSummary } from "@/components/AccountCharts";

// Los precios se ven SIN cuenta a propósito: quien llega de una publicación
// tiene que poder saber cuánto sale antes de que le pidan registrarse. Era el
// agujero de la navegación —el único lugar donde se podía comprar estaba dentro
// de una carta ya generada, y los packs no se podían comprar en ningún lado—.

// Lo que dice cada botón del selector. Acá y no en los diccionarios: es el
// símbolo de la moneda, igual en los tres idiomas (y `check` prohíbe el
// literal en los textos).
// Los pesos con «AR$» y no «$»: el selector se ve en los tres idiomas, y en
// inglés «$» es el dólar.
const SIMBOLO: Record<(typeof MONEDAS)[number], string> = { usd: "US$", brl: "R$", ars: "AR$" };

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
    title: `${dict.precios.seoTitle} · ASTRA`,
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
      title: `${dict.precios.seoTitle} · ASTRA`,
      description: dict.precios.lede,
      url: `${SITE_URL}/${locale}/precios`,
    },
    twitter: {
      card: "summary_large_image",
      title: `${dict.precios.seoTitle} · ASTRA`,
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
  const query = await searchParams;
  // El cupón que trae la URL, por link o por el campo. Se valida en el
  // backend —la misma función que cobra— y sólo con forma de código: lo
  // demás ni se consulta. Sin respuesta, precio de lista.
  const codigoCupon = normalizarCupon(query.cupon);
  const [productos, signedIn, cupon, moneda] = await Promise.all([
    fetchCatalogo(),
    haySesion(),
    codigoCupon ? fetchCupon(codigoCupon) : Promise.resolve(null),
    // RF25: la del selector (cookie) o la de la IP. Cada producto se muestra
    // —y se cobra— en esa si tiene precio en ella, si no en dólares (EC2).
    monedaDelVisitante(),
  ]);
  // Si la cuenta tiene alguna carta, sólo con sesión: decide si la tarjeta
  // tiene que explicar qué pasa después de pagar sin una. El listado viene
  // como `{ results: [...] }`, igual que lo lee la cuenta. Si falla, se asume
  // que hay —la nota de más es ruido, la de menos no rompe nada—.
  const hayCartas: boolean = signedIn
    ? await callApi<{ results: ChartSummary[] }>("/api/charts/")
        .then((r) => r.results.length > 0)
        .catch(() => true)
    : true;
  // La moneda que de verdad se ve: la pedida (cookie o IP) si el catálogo la
  // ofrece, si no dólares. Con pesos pedidos y el cobro en pesos apagado se
  // cobra en dólares con Stripe, y el selector y la nota lo tienen que decir.
  const ofrecidas = monedasOfrecidas(productos);
  const monedaVista = ofrecidas.includes(moneda) ? moneda : "usd";
  const cuponValido = cupon?.valido ? cupon : null;
  const estadoCupon = cupon === null ? null : cupon.valido ? "valido" : cupon.motivo;
  // El precio final por producto, sólo para los que el cupón abarca, en la
  // moneda en que se muestra ese producto.
  const finales = new Map(
    (cuponValido?.productos ?? []).map((p) => {
      const m = monedaPara(p, moneda);
      return [p.codigo, p.finales?.[m]?.precio_final_centavos ?? p.precio_final_centavos];
    }),
  );
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
    itemListElement: productos.map((producto, i) => {
      const [centavos, enMoneda] = precioEn(producto, moneda);
      return {
      "@type": "ListItem",
      position: i + 1,
      item: {
        "@type": "Product",
        name: dict.precios.nombre[producto.codigo] ?? producto.codigo,
        description: dict.precios.detalle[producto.codigo] ?? "",
        offers: {
          "@type": "Offer",
          price: (centavos / 100).toFixed(2),
          priceCurrency: enMoneda.toUpperCase(),
          availability: "https://schema.org/InStock",
          url: `${SITE_URL}/${locale}/precios`,
        },
      },
      };
    }),
  };

  return (
    <>
      <Nav locale={locale} dict={dict} path="/precios" signedIn={signedIn} />

      <main className="docFrame preciosFrame">
        <section className="preciosHead">
          <h1 className="display">{dict.precios.title}</h1>
          <p className="preciosLede">{dict.precios.lede}</p>
          {/* RF24: un formulario común, sin JS. Guarda la elección en una
              cookie y vuelve acá; todas las páginas con precio la leen. */}
          <form className="switch monedaSelector" action="/api/moneda" method="post" aria-label={dict.precios.monedaLabel}>
            <input type="hidden" name="volver" value={`/${locale}/precios`} />
            {codigoCupon && <input type="hidden" name="cupon" value={codigoCupon} />}
            {ofrecidas.map((m) => (
              <button
                key={m}
                type="submit"
                name="moneda"
                value={m}
                aria-pressed={m === monedaVista}
              >
                {SIMBOLO[m]}
              </button>
            ))}
          </form>
        </section>

        {/* Antes de todo lo que se cobra, y fuera de la grilla: no es un producto
            con su tarjeta, es el punto de partida. El catálogo público no la
            trae —vale cero—, así que sin escribirla acá la página decía que
            para probar ASTRA había que pagar el informe, que es falso y es lo
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

        {/* El cupón y la grilla en una misma sección: lo que diga el cupón
            cambia los precios, y separados por el aire que el marco pone
            entre hermanos parecía un formulario perdido. */}
        <section className="preciosOferta">
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
              const [lista, enMoneda] = precioEn(producto, moneda);
              const precio = formatearPrecio(lista, enMoneda, INTL_LOCALE[locale]);
              const final = finales.get(producto.codigo);
              return (
                <li key={producto.codigo} className="precioCard">
                  <h2 className="precioNombre">
                    {dict.precios.nombre[producto.codigo] ?? producto.codigo}
                  </h2>
                  {final === undefined ? (
                    <p className="precioMonto">{precio}</p>
                  ) : (
                    // La lista tachada y el final al lado: el descuento se ve
                    // ANTES de ir a pagar, que es lo que pide el cupón.
                    <p className="precioMonto">
                      <s className="precioTachado">{precio}</s>{" "}
                      {formatearPrecio(final, enMoneda, INTL_LOCALE[locale])}
                    </p>
                  )}
                  {n > 1 && (
                    // Lo que hace comparable un pack con el suelto: sin esto,
                    // "US$ 125" al lado de "US$ 29" parece más caro.
                    <p className="precioUnidad">
                      {dict.precios.porUnidad.replace(
                        "{precio}",
                        // Sobre lo que se paga: con cupón, «US$ 25 cada uno»
                        // al lado de US$ 87,50 era la cuenta del precio viejo.
                        formatearPrecio(
                          Math.round((final ?? lista) / n),
                          enMoneda,
                          INTL_LOCALE[locale],
                        ),
                      )}
                    </p>
                  )}
                  <p className="precioDetalle">
                    {dict.precios.detalle[producto.codigo] ?? ""}
                  </p>
                  <ComprarBoton
                    moneda={monedaPara(producto, moneda)}
                    codigo={producto.codigo}
                    locale={locale}
                    dict={dict}
                    signedIn={signedIn}
                    reanudar={pedido === producto.codigo}
                    cupon={final === undefined ? null : cuponValido?.codigo}
                  />
                  {signedIn && !hayCartas && (
                    <p className="fieldNote">{dict.precios.sinCartaNota}</p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {/* Debajo de la grilla: arriba, «Tengo un cupón» flotaba sobre la
            tarjeta como si fuera su título. */}
        <CuponInput
          locale={locale}
          dict={dict}
          inicial={codigoCupon}
          estado={codigoCupon ? estadoCupon : null}
          porcentaje={cuponValido?.porcentaje}
        />
        </section>

        {/* Los dos juntos en un hijo del marco: `.docFrame` separa a sus hijos
            directos con 3-4,5rem, así que el enlace suelto quedaba a media
            pantalla de la nota que acompaña. */}
        <div className="preciosPie">
          <p className="preciosNota">{monedaVista === "ars" ? dict.precios.notaPesos : dict.precios.nota}</p>
          {/* En su propia línea, no colgando del final: nadie compra 6.000
              palabras a ciegas, y esto es una invitación a mirar el producto,
              no una aclaración más sobre impuestos. */}
          <p className="preciosEjemplo">
            <Link href={`/${locale}/ejemplo`}>{dict.precios.verEjemplo}</Link>
          </p>
        </div>
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
