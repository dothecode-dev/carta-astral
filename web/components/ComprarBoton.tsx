"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

/**
 * Comprar un producto suelto, sin carta atada.
 *
 * Es la diferencia con el botón de la carta (`ChartActions`), que compra el
 * informe PARA esa carta y por eso el webhook lo arranca solo. Acá se compra
 * el derecho y se usa después, en la carta que la persona quiera: el botón de
 * la carta ya sabe leer con un derecho existente en vez de cobrar de nuevo.
 *
 * Sin sesión no se intenta el pago: se manda a entrar. El backend igual
 * rechazaría con 401 —el checkout exige cuenta, porque el derecho tiene que
 * quedar guardado en algún lado—, pero mostrar un error después de hacer clic
 * en "Comprar" es peor que decirlo antes.
 */
export function ComprarBoton({
  codigo,
  locale,
  dict,
  signedIn,
  reanudar = false,
}: {
  codigo: string;
  locale: Locale;
  dict: Dict;
  signedIn: boolean;
  /** Este es el producto que la persona había pedido antes de que el login se
   *  interpusiera: se abre el checkout sola, sin pedirle el mismo clic dos
   *  veces. Lo decide la página, comparando el `?comprar=` contra el catálogo
   *  real — acá ya llega resuelto. */
  reanudar?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const comprar = useCallback(async () => {
    setBusy(true);
    setError(null);
    // Antes de salir del sitio: lo que sigue es una redirección a Stripe, y si
    // el checkout no abre igual interesa saber que alguien quiso comprar.
    track("checkout_iniciado", { producto: codigo, desde: "precios" });
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ producto: codigo, locale }),
      });
      if (res.status === 401) {
        // La sesión se venció mientras miraba la página. `haySesion()` sólo
        // mira que la cookie exista —para no pegarle al backend en cada página
        // pública—, así que /precios igual pintó el botón "Comprar". Mostrar
        // acá "no pudimos abrir el pago" era echarse la culpa de algo que
        // reintentar no arregla nunca, y justo en el momento de pagar.
        //
        // Va por la ruta que BORRA la cookie muerta: mandarlo derecho a
        // /entrar la dejaría viva y volvería a rebotar. Y lleva a dónde volver
        // y qué compraba, así el checkout se reabre solo después del login.
        window.location.assign(
          `/api/session/expirada?locale=${locale}&next=${encodeURIComponent(
            `/${locale}/precios`,
          )}&comprar=${encodeURIComponent(codigo)}`,
        );
        return;
      }
      if (!res.ok) {
        setBusy(false);
        setError(dict.precios.fallo);
        return;
      }
      const { url } = (await res.json()) as { url: string };
      // El checkout de Stripe es otro sitio: no es una navegación de Next.
      window.location.assign(url);
    } catch {
      setBusy(false);
      setError(dict.precios.fallo);
    }
  }, [codigo, locale, dict.precios.fallo]);

  // Una sola vez por montaje: sin el guard, volver de Stripe con el botón
  // "atrás" —que restaura la URL con `?comprar=` incluido— relanzaría el
  // checkout de quien justo acababa de decidir que no.
  const reanudado = useRef(false);
  useEffect(() => {
    if (!reanudar || !signedIn || reanudado.current) return;
    reanudado.current = true;
    // Se borra el rastro antes de salir del sitio, por la misma razón: la URL
    // a la que se vuelve ya no pide comprar nada.
    window.history.replaceState(null, "", `/${locale}/precios`);
    void comprar();
  }, [reanudar, signedIn, locale, comprar]);

  if (!signedIn) {
    return (
      <Link
        className="btn btnPrimary"
        // Con qué venía y a dónde volver. Sin esto el login lo dejaba en su
        // cuenta vacía y la compra se perdía en el camino.
        href={`/${locale}/entrar?next=${encodeURIComponent(
          `/${locale}/precios`,
        )}&comprar=${encodeURIComponent(codigo)}`}
      >
        {dict.precios.comprar}
      </Link>
    );
  }

  return (
    <>
      {/* Antes del botón, no después: el detalle de arriba tiene `flex: 1` y
          empuja el botón al pie de la tarjeta, así que un error debajo lo
          levantaba y los tres botones dejaban de estar a la misma altura.
          Acá el error se come parte del espacio flexible y el botón no se
          mueve — y de paso se lee antes de volver a apretarlo. */}
      {error && (
        <p className="compraError" role="alert">
          {error}
        </p>
      )}
      <button type="button" className="btn btnPrimary" disabled={busy} onClick={comprar}>
        {busy ? dict.precios.abriendo : dict.precios.comprar}
      </button>
    </>
  );
}
