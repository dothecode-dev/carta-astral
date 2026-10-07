"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import { abreviar } from "@/lib/compraCookie";
import type { Dict, Locale } from "@/lib/i18n";
import { identificar } from "@/lib/telemetry";

// La vuelta del pago de quien compró sin cuenta (RF13, RF14 de «pagar es
// entrar»). Hermana de `CompraEspera`, que es la de quien compró con sesión.
//
// Le pregunta al canje (`/api/compra/canjear`, que lee el nonce de la cookie
// httpOnly de este checkout: acá no se ve) y, según lo que conteste:
// - `sesion`: la compra creó la cuenta y la sesión ya está puesta. A la carta.
// - `codigo`: la cuenta ya existía y se le mandó un código a su mail. Se lo
//   dice y lo manda a `/entrar` a escribir el mail y el código (ver abajo).
// - `pendiente`: el webhook todavía no acreditó. Se vuelve a preguntar.
// - `invalido`: no hay canje posible. Se lo manda a su cuenta.
//
// Sólo `pendiente` se vuelve a preguntar. Repetir el canje después de `codigo`
// pediría otro mail; después de `sesion` o `invalido` ya no hay nada que
// preguntar.
//
// Por qué un enlace a `/entrar` y no el formulario del código acá mismo:
// `EntrarPorMail` canjea el código con el mail COMPLETO, y el backend sólo nos
// da el enmascarado —a propósito: quien vuelve de pagar con el mail de otro no
// tiene por qué verlo—. Reescribir el mail en `/entrar` es un paso más, pero
// es el mismo formulario que ya funciona, y pedir el código de nuevo ahí no
// manda uno distinto: el backend devuelve el mismo mientras esté vigente.

/** Cada cuánto se vuelve a preguntar mientras el pago está pendiente. */
export const POLL_MS = 3000;
/** Cuántas veces: 2 minutos. Más que `CompraEspera` porque acá también caen
 *  los pagos asincrónicos, que tardan más que una tarjeta. */
export const POLL_TRIES = 40;

type Respuesta =
  | { estado: "sesion"; destino?: string; account_id?: number }
  | { estado: "codigo"; email?: string; destino?: string }
  | { estado: "pendiente" }
  | { estado: "invalido" };

type Vista =
  | { tipo: "esperando" }
  | { tipo: "codigo"; email: string; destino: string | null }
  | { tipo: "proceso" }
  | { tipo: "invalido" };

/** El destino lo valida la ruta del servidor contra la lista cerrada de
 *  `/entrar`; esto es la segunda red, por si algún día alguien la saltea: una
 *  ruta del sitio, nunca otro dominio. */
function destinoLocal(destino: unknown): string | null {
  if (typeof destino !== "string" || !destino.startsWith("/")) return null;
  if (destino.startsWith("//") || destino.includes("\\")) return null;
  return destino;
}

export function CanjeCompra({
  locale,
  checkoutId,
  dict,
}: {
  locale: Locale;
  checkoutId: string;
  dict: Dict;
}) {
  const router = useRouter();
  const [vista, setVista] = useState<Vista>({ tipo: "esperando" });

  useEffect(() => {
    let cancelado = false;

    (async () => {
      for (let intento = 0; intento < POLL_TRIES; intento++) {
        try {
          const res = await fetch("/api/compra/canjear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ checkout_id: checkoutId }),
          });
          if (res.ok) {
            const datos = (await res.json()) as Respuesta;
            if (cancelado) return;
            if (datos.estado === "sesion") {
              if (typeof datos.account_id === "number") identificar(datos.account_id);
              // `replace`: volver atrás desde la carta no tiene que traer a
              // esta pantalla de paso. `refresh`: el header tiene que ver la
              // sesión nueva.
              router.replace(destinoLocal(datos.destino) ?? `/${locale}/cuenta`);
              router.refresh();
              return;
            }
            if (datos.estado === "codigo") {
              setVista({ tipo: "codigo", email: datos.email ?? "", destino: destinoLocal(datos.destino) });
              return;
            }
            if (datos.estado === "invalido") {
              setVista({ tipo: "invalido" });
              return;
            }
            // `pendiente`: a esperar y volver a preguntar.
          }
          // Un 429 o un 502 son pasajeros: cuentan como un intento más.
        } catch (err) {
          // Un corte de red tampoco termina la espera.
          console.error("canje de la compra", err);
        }
        if (intento < POLL_TRIES - 1) await new Promise((r) => window.setTimeout(r, POLL_MS));
        if (cancelado) return;
      }
      if (!cancelado) setVista({ tipo: "proceso" });
    })();

    return () => {
      cancelado = true;
    };
  }, [checkoutId, locale, router]);

  if (vista.tipo === "codigo") {
    const entrar = vista.destino
      ? `/${locale}/entrar?next=${encodeURIComponent(vista.destino)}`
      : `/${locale}/entrar`;
    return (
      <section className="waiting">
        <div className="waitingCopy">
          <h1 className="display waitingTitle">
            {dict.compra.canjeCodigoTitle.replace("{email}", vista.email)}
          </h1>
          <p className="waitingBody">{dict.compra.canjeCodigoBody}</p>
          <Link className="btn btnPrimary" href={entrar}>
            {dict.compra.canjeEntrar}
          </Link>
          <p className="fieldNote">{dict.compra.canjeSoporte.replace("{numero}", abreviar(checkoutId))}</p>
        </div>
      </section>
    );
  }

  if (vista.tipo === "proceso" || vista.tipo === "invalido") {
    const proceso = vista.tipo === "proceso";
    return (
      <section className="waiting">
        <div className="waitingCopy">
          <h1 className="display waitingTitle">
            {proceso ? dict.compra.canjeProcesoTitle : dict.compra.canjeInvalidoTitle}
          </h1>
          <p className="waitingBody">{proceso ? dict.compra.canjeProcesoBody : dict.compra.canjeInvalidoBody}</p>
          <Link className="btn btnPrimary" href={`/${locale}/cuenta`}>
            {dict.compra.irACuenta}
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="waiting">
      <SolarSystem size={280} speed={2.5} />
      <div className="waitingCopy">
        <h1 className="display waitingTitle">{dict.compra.title}</h1>
        <p className="waitingBody">{dict.compra.body}</p>
      </div>
    </section>
  );
}
