import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { EntrarPorMail } from "@/components/EntrarPorMail";
import { EntrarVisto } from "@/components/EntrarVisto";
import { GoogleSignIn } from "@/components/GoogleSignIn";
import { Nav } from "@/components/Nav";
import { normalizarCupon } from "@/lib/cupon";
import { destinoSeguro } from "@/lib/destino";
import { LOCALES, getDict, isLocale } from "@/lib/i18n";
import { sessionIsLive } from "@/lib/session";
import { Footer } from "@/components/Footer";

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
  return {
    title: `${getDict(locale).auth.title} — ASTRA`,
    // Una pantalla de acceso no aporta nada a una búsqueda.
    robots: { index: false, follow: true },
  };
}

/** El producto que se venía a comprar, si es que se venía a eso.
 *
 *  No se valida contra el catálogo acá —esta pantalla no lo tiene y pedirlo
 *  sólo para esto sería una llamada de red por login—: la forma alcanza para
 *  que no se pueda colar nada en la URL de destino, y /precios ignora un código
 *  que no exista. */
function productoPedido(comprar: unknown): string | null {
  return typeof comprar === "string" && /^[a-z0-9_]{1,40}$/.test(comprar) ? comprar : null;
}

export default async function SignInPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const query = await searchParams;
  const destino = destinoSeguro(query.next, locale);
  const producto = productoPedido(query.comprar);
  // El cupón con el que llegó, si tiene forma de código: /precios lo vuelve a
  // validar contra el backend, acá sólo se cuida que no se cuele otra cosa.
  const cupon = normalizarCupon(query.cupon);
  // La compra viaja aparte de la ruta: `destinoSeguro` rechaza cualquier `next`
  // con query justamente para no tener que razonar sobre lo que venga pegado.
  const extras = [
    producto ? `comprar=${encodeURIComponent(producto)}` : null,
    cupon ? `cupon=${encodeURIComponent(cupon)}` : null,
  ].filter(Boolean);
  const volverA = destino && extras.length ? `${destino}?${extras.join("&")}` : destino;

  // Quien ya entró no tiene nada que hacer acá. Se le pregunta al backend en
  // vez de confiar en que exista la cookie: una cookie que él ya no reconoce
  // mandaba a /cuenta, que rebotaba para acá, y así hasta la pantalla en blanco.
  if (await sessionIsLive()) redirect(volverA ?? `/${locale}/cuenta`);

  const dict = getDict(locale);

  return (
    <>
      <Nav locale={locale} dict={dict} path="/entrar" />

      <main className="docFrame authFrame">
        {/* Sólo el destino ya validado por `destinoSeguro`, sin los extras de
            compra/cupón que se le pegan abajo: nada de eso viaja al evento. */}
        <EntrarVisto next={destino} />

        <section className="authCard">
          <h1 className="display authTitle">{dict.auth.title}</h1>
          <p className="authLede">{dict.auth.lede}</p>

          {/* Google primero: es la única puerta con resultado conocido hoy
              (Ruling 5). Apple entra ACÁ ENTRE MEDIO en la Tarea 14, con su
              propio divisor — este bloque no se reescribe para eso, se inserta.

              Cada puerta lleva su título oculto: en la pantalla se distinguen
              solas —un botón de Google y un campo de mail—, pero quien navega
              por encabezados encontraba un botón y después un campo sin nada
              que dijera que son dos caminos al mismo lugar. */}
          <h2 className="srOnly">{dict.auth.puertaGoogle}</h2>
          <GoogleSignIn
            locale={locale}
            next={volverA}
            labels={{
              loading: dict.auth.loading,
              blocked: dict.auth.blocked,
              failed: dict.auth.failed,
            }}
          />

          <div className="authDivider">{dict.auth.oBien}</div>

          <h2 className="srOnly">{dict.auth.puertaMail}</h2>
          <EntrarPorMail
            locale={locale}
            next={volverA}
            labels={{
              mailLabel: dict.auth.mailLabel,
              mailPlaceholder: dict.auth.mailPlaceholder,
              mailButton: dict.auth.mailButton,
              codigoLabel: dict.auth.codigoLabel,
              codigoPlaceholder: dict.auth.codigoPlaceholder,
              codigoHelp: dict.auth.codigoHelp,
              codigoButton: dict.auth.codigoButton,
              enviando: dict.auth.enviando,
              reenviar: dict.auth.reenviar,
              cambiarMail: dict.auth.cambiarMail,
              codigoInvalido: dict.auth.codigoInvalido,
              demasiadosIntentos: dict.auth.demasiadosIntentos,
              noDisponible: dict.auth.noDisponible,
              errorRed: dict.auth.errorRed,
            }}
          />

          <p className="authLegal">
            {dict.auth.legal}{" "}
            <Link href={`/${locale}/legal/terms`}>{dict.foot.terms}</Link>
            {" · "}
            <Link href={`/${locale}/legal/privacy`}>{dict.foot.privacy}</Link>
          </p>
        </section>
      </main>

      <Footer locale={locale} dict={dict} />
    </>
  );
}
