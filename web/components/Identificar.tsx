"use client";

import { useEffect, useRef } from "react";

import { identificar } from "@/lib/telemetry";

/**
 * Ata los eventos de este navegador a la cuenta, en cualquier página que ya
 * tenga la sesión resuelta en el servidor.
 *
 * Hasta el 08-09-2026 esto vivía sólo en `GoogleSignIn`, o sea que sólo se
 * identificaba a quien acababa de loguearse. La cookie de sesión dura noventa
 * días: quien vuelve al día siguiente —o desde otro dispositivo— no pasa por el
 * login y navegaba anónimo. La primera persona que compró apareció por eso
 * partida en dos personas de PostHog, con el checkout en una y la compra en la
 * otra, y el embudo por unique users marcando cero ventas.
 *
 * No cuesta una request: el `account_id` ya viene en `/api/account/`, que esas
 * páginas piden igual. Y no se pone en el layout a propósito — leer la sesión
 * ahí obligaría a `cookies()` y sacaría del prerender a la home y a las notas.
 *
 * `identify` sin consentimiento no hace nada: `identificar()` sale temprano si
 * PostHog no se inicializó, que es lo que pasa mientras no se acepte el banner.
 * PostHog une hacia atrás los eventos anónimos de este mismo navegador, así que
 * identificar una vez por visita alcanza para recuperar lo ya ocurrido.
 */
export function Identificar({ accountId }: { accountId?: number }) {
  const identificado = useRef<number | null>(null);

  useEffect(() => {
    if (typeof accountId !== "number") return;
    if (identificado.current === accountId) return;
    identificado.current = accountId;
    identificar(accountId);
  }, [accountId]);

  return null;
}
