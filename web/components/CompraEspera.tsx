"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import type { Dict, Locale } from "@/lib/i18n";

// Adónde va quien vuelve de pagar.
//
// Existe por una carrera que no se puede evitar: Polar redirige el navegador al
// instante y su webhook —el que acredita la compra y arranca el informe— puede
// llegar unos segundos después. Esta pantalla espera esa confirmación y recién
// entonces manda a la carta o a la cuenta, según lo que se haya comprado.
//
// Mandar de una a la carta sin esperar sería mostrarle el botón de comprar a
// alguien que acaba de pagar: exactamente el bug que costó el 02-09-2026.

/** Cada cuánto se pregunta si el pago ya está confirmado. */
export const POLL_MS = 2000;
/**
 * Cuántas veces, antes de dejar de esperar: 45 segundos.
 *
 * El webhook normal tarda segundos. Este tope es para cuando algo salió mal, y
 * lo que sigue no es un error rojo sino la verdad —el pago se hizo, la
 * confirmación no llegó— con dónde seguir. Girar para siempre después de que
 * alguien puso US$ 29 es la peor salida posible.
 */
export const POLL_TRIES = 22;

type Destino = { tipo: "carta"; id: string } | { tipo: "cuenta" };
type Estado = { estado: "pendiente" | "acreditado"; destino?: Destino };

export function CompraEspera({
  locale,
  checkoutId,
  dict,
}: {
  locale: Locale;
  checkoutId: string;
  dict: Dict;
}) {
  const router = useRouter();
  const [seRindio, setSeRindio] = useState(false);

  useEffect(() => {
    let cancelado = false;

    (async () => {
      for (let intento = 0; intento < POLL_TRIES; intento++) {
        try {
          const res = await fetch(`/api/compra?checkout_id=${encodeURIComponent(checkoutId)}`);
          if (res.ok) {
            const datos = (await res.json()) as Estado;
            if (datos.estado === "acreditado") {
              if (cancelado) return;
              // `replace` y no `push`: volver atrás desde la carta tiene que
              // llevar a donde estaba antes de pagar, no a esta pantalla de
              // paso —que ya no tendría nada que esperar—.
              router.replace(
                datos.destino?.tipo === "carta"
                  ? `/${locale}/carta/${datos.destino.id}`
                  : `/${locale}/cuenta`,
              );
              return;
            }
          } else if (res.status === 401) {
            // La sesión se venció mientras pagaba: que entre y vuelva a su
            // cuenta, donde va a estar lo que compró.
            if (!cancelado) router.replace(`/${locale}/entrar`);
            return;
          } else if (res.status === 404) {
            // Un checkout que no es de esta cuenta, o un link viejo. No hay
            // nada que esperar: la cuenta es el lugar donde mirar.
            break;
          }
        } catch (err) {
          // Un corte de red no es el fin: se cuenta como un intento más. Sin
          // este catch, la excepción rompía el bucle y dejaba la animación
          // girando para siempre.
          console.error("consulta del estado de la compra", err);
        }
        await new Promise((r) => window.setTimeout(r, POLL_MS));
      }
      if (!cancelado) setSeRindio(true);
    })();

    return () => {
      cancelado = true;
    };
  }, [checkoutId, locale, router]);

  if (seRindio) {
    return (
      <section className="waiting">
        <div className="waitingCopy">
          <h1 className="display waitingTitle">{dict.compra.demoraTitle}</h1>
          <p className="waitingBody">{dict.compra.demoraBody}</p>
          <Link className="btn btnPrimary" href={`/${locale}/cuenta`}>
            {dict.compra.irACuenta}
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="waiting">
      <SolarSystem size={200} speed={2.5} />
      <div className="waitingCopy">
        <h1 className="display waitingTitle">{dict.compra.title}</h1>
        <p className="waitingBody">{dict.compra.body}</p>
      </div>
    </section>
  );
}
