"use client";

import Link from "next/link";
import { useState } from "react";

import type { Dict, Locale } from "@/lib/i18n";

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
}: {
  codigo: string;
  locale: Locale;
  dict: Dict;
  signedIn: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!signedIn) {
    return (
      <Link className="btn btnPrimary" href={`/${locale}/entrar`}>
        {dict.precios.comprar}
      </Link>
    );
  }

  async function comprar() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ producto: codigo, locale }),
      });
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
  }

  return (
    <>
      <button type="button" className="btn btnPrimary" disabled={busy} onClick={comprar}>
        {busy ? dict.precios.abriendo : dict.precios.comprar}
      </button>
      {error && (
        <p className="fieldNote" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
