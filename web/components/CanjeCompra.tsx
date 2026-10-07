"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EntrarPorMail } from "@/components/EntrarPorMail";
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
//   dice y le muestra acá mismo el formulario de mail + código (ver abajo).
// - `pendiente`: el webhook todavía no acreditó. Se vuelve a preguntar.
// - `invalido`: no hay canje posible. Se lo manda a su cuenta.
//
// Sólo `pendiente` se vuelve a preguntar. Repetir el canje después de `codigo`
// pediría otro mail; después de `sesion` o `invalido` ya no hay nada que
// preguntar.
//
// El formulario del código va acá y no en `/entrar`, por dos razones:
// - `/entrar` empieza pidiendo el código, y el backend crea uno NUEVO en cada
//   pedido (`codigos_acceso.pedir`): sería un segundo mail y un pedido más
//   contra el techo por hora, para un código que ya salió.
// - Con la sesión de otra cuenta abierta, `/entrar` redirige sin mostrar nada,
//   y quien pagó nunca llegaría a escribir su código (RF14: con o sin sesión).
// Es `EntrarPorMail` en modo `codigoYaEnviado`: mail y código en el mismo
// paso, sin pedir nada al montar. El mail completo lo escribe la persona —el
// backend sólo da el enmascarado, a propósito: quien pagó con el mail de otro
// no tiene por qué verlo—. El canje del código pasa por `/api/session`, que
// reemplaza la sesión que hubiera. «Reenviar» sí pide uno nuevo.
//
// Un solo canje en vuelo por checkout: en desarrollo React monta los efectos
// dos veces (StrictMode), y dos canjes simultáneos terminan con el primero
// ganando `sesion` —con la cookie ya puesta por el servidor— y el segundo en
// 404. Por eso el pedido se comparte (`enVuelo`) y un `sesion` nunca se
// descarta, aunque el efecto que lo pidió ya se haya limpiado.

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

/** El canje en curso de cada checkout. Lo comparten las dos corridas del
 *  efecto en StrictMode (y cualquier otra instancia montada a la vez). */
const enVuelo = new Map<string, Promise<Respuesta | null>>();

/** Un canje, o el que ya está en vuelo para ese checkout. `null` es una
 *  falla pasajera (429, 502, red): cuenta como un intento más. */
function canjear(checkoutId: string): Promise<Respuesta | null> {
  const ya = enVuelo.get(checkoutId);
  if (ya) return ya;
  const pedido = (async () => {
    try {
      const res = await fetch("/api/compra/canjear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checkout_id: checkoutId }),
      });
      return res.ok ? ((await res.json()) as Respuesta) : null;
    } catch (err) {
      console.error("canje de la compra", err);
      return null;
    } finally {
      enVuelo.delete(checkoutId);
    }
  })();
  enVuelo.set(checkoutId, pedido);
  return pedido;
}

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
        const datos = await canjear(checkoutId);
        if (datos?.estado === "sesion") {
          // Aunque este efecto ya se haya limpiado: el servidor ya puso la
          // cookie de sesión y el nonce se borró, así que otro canje daría
          // `invalido`. Descartarlo dejaría a quien pagó afuera.
          if (typeof datos.account_id === "number") identificar(datos.account_id);
          // `replace`: volver atrás desde la carta no tiene que traer a esta
          // pantalla de paso. `refresh`: el header tiene que ver la sesión.
          router.replace(destinoLocal(datos.destino) ?? `/${locale}/cuenta`);
          router.refresh();
          return;
        }
        // El resto lo resuelve la corrida viva, que recibe la misma respuesta.
        if (cancelado) return;
        if (datos?.estado === "codigo") {
          setVista({ tipo: "codigo", email: datos.email ?? "", destino: destinoLocal(datos.destino) });
          return;
        }
        if (datos?.estado === "invalido") {
          setVista({ tipo: "invalido" });
          return;
        }
        // `pendiente` o una falla pasajera: a esperar y volver a preguntar.
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
    const auth = dict.auth;
    return (
      <section className="waiting">
        <div className="waitingCopy">
          <h1 className="display waitingTitle">
            {dict.compra.canjeCodigoTitle.replace("{email}", vista.email)}
          </h1>
          <p className="waitingBody">{dict.compra.canjeCodigoBody}</p>
          <EntrarPorMail
            locale={locale}
            next={vista.destino}
            codigoYaEnviado
            labels={{
              mailLabel: auth.mailLabel,
              mailPlaceholder: auth.mailPlaceholder,
              mailButton: auth.mailButton,
              codigoLabel: auth.codigoLabel,
              codigoPlaceholder: auth.codigoPlaceholder,
              codigoHelp: auth.codigoHelp,
              codigoButton: auth.codigoButton,
              enviando: auth.enviando,
              reenviar: auth.reenviar,
              cambiarMail: auth.cambiarMail,
              codigoInvalido: auth.codigoInvalido,
              demasiadosIntentos: auth.demasiadosIntentos,
              noDisponible: auth.noDisponible,
              errorRed: auth.errorRed,
            }}
          />
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
