"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { CartaDibujable } from "@/lib/chart";
import type { Locale } from "@/lib/i18n";
import { guardarLectura, type LecturaGuardada } from "@/lib/lecturaLocal";
import { track } from "@/lib/telemetry";

// El pedido de la lectura breve sin cuenta y la espera (spec 2026-10-08,
// RF12, RF16). La consulta va con backoff y corta a los 60 s; un «ocupado»
// se reintenta solo, sin que la persona haga nada.
//
// EXCEPCIÓN a `rutasApiSinFetchDirecto.test.ts`: este hook corre en el
// NAVEGADOR y le pega a `/api/lectura-anonima`, la ruta de Next, no al
// backend. Quien reenvía la IP con `callApi` es esa ruta; acá no hay
// `headers()` de servidor que usar.

export type EstadoLectura =
  | { tipo: "nada" }
  | { tipo: "esperando"; ocupado: boolean }
  | { tipo: "lista"; texto: string; lang: Locale; disclaimer: string }
  | { tipo: "usada" }
  | { tipo: "sin_cupo" }
  | { tipo: "fallida" }
  | { tipo: "mantenimiento" };

const ESPERAS_MS = [1000, 2000, 4000];
const ESPERA_MAX_MS = 4000;
const CORTE_MS = 60_000;
const REINTENTO_OCUPADO_MS = 5000;
const REINTENTOS_OCUPADO = 3;

type Motivo = "modelo" | "ip" | "cupo" | "ocupado" | "mantenimiento" | "timeout";

export function useLecturaAnonima() {
  const [estado, setEstado] = useState<EstadoLectura>({ tipo: "nada" });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const vivo = useRef(true);
  // Las dos funciones se llaman a sí mismas desde un timer: la referencia
  // evita que una `useCallback` se nombre dentro de su propia definición.
  const consultarRef = useRef<(carta: CartaDibujable, intento: number, inicio: number) => void>(() => {});
  const pedirRef = useRef<(c: object, k: CartaDibujable, l: Locale, r: number) => Promise<void>>(
    async () => {},
  );

  useEffect(() => {
    vivo.current = true;
    return () => {
      vivo.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const fallar = useCallback((motivo: Motivo, siguiente: EstadoLectura = { tipo: "fallida" }) => {
    track("lectura_anonima_fallida", { motivo });
    setEstado(siguiente);
  }, []);

  const consultar = useCallback(
    (carta: CartaDibujable, intento: number, inicio: number) => {
      // La espera nunca pasa del corte: sin el tope, el último sondeo caía
      // hasta 4 s después de los 60 s y el aviso llegaba tarde.
      const espera = Math.min(
        ESPERAS_MS[intento] ?? ESPERA_MAX_MS,
        Math.max(0, inicio + CORTE_MS + 1 - Date.now()),
      );
      timer.current = setTimeout(async () => {
        if (!vivo.current) return;
        if (Date.now() - inicio > CORTE_MS) return fallar("timeout");
        try {
          const r = await fetch("/api/lectura-anonima");
          const cuerpo = (await r.json()) as { estado?: string; texto?: string; lang?: Locale; disclaimer?: string };
          if (r.ok && cuerpo.estado === "lista" && cuerpo.texto && cuerpo.lang) {
            const lista = { texto: cuerpo.texto, lang: cuerpo.lang, disclaimer: cuerpo.disclaimer ?? "" };
            guardarLectura({ carta, ...lista });
            track("lectura_anonima_generada", {});
            setEstado({ tipo: "lista", ...lista });
            return;
          }
          if (r.ok && cuerpo.estado === "fallida") return fallar("modelo");
          if (!r.ok) return fallar("modelo");
          consultarRef.current(carta, intento + 1, inicio);
        } catch {
          consultarRef.current(carta, intento + 1, inicio);
        }
      }, espera);
    },
    [fallar],
  );

  const pedir = useCallback(
    async (cuerpo: object, carta: CartaDibujable, lang: Locale, reintento = 0): Promise<void> => {
      if (reintento === 0) track("lectura_anonima_pedida", {});
      setEstado({ tipo: "esperando", ocupado: reintento > 0 });
      let r: Response;
      try {
        r = await fetch("/api/lectura-anonima", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...cuerpo, lang }),
        });
      } catch {
        return fallar("modelo");
      }
      if (r.status === 202) return consultar(carta, 0, Date.now());
      const { motivo } = (await r.json().catch(() => ({}))) as { motivo?: string };
      if (r.status === 409) {
        track("lectura_anonima_usada", {});
        return setEstado({ tipo: "usada" });
      }
      if (r.status === 429) return fallar("ip", { tipo: "sin_cupo" });
      if (motivo === "cupo") return fallar("cupo", { tipo: "sin_cupo" });
      if (motivo === "mantenimiento") return fallar("mantenimiento", { tipo: "mantenimiento" });
      if (motivo === "ocupado") {
        if (reintento >= REINTENTOS_OCUPADO) return fallar("ocupado");
        setEstado({ tipo: "esperando", ocupado: true });
        timer.current = setTimeout(() => {
          if (vivo.current) void pedirRef.current(cuerpo, carta, lang, reintento + 1);
        }, REINTENTO_OCUPADO_MS);
        return;
      }
      fallar("modelo");
    },
    [consultar, fallar],
  );

  useEffect(() => {
    consultarRef.current = consultar;
    pedirRef.current = pedir;
  }, [consultar, pedir]);

  const mostrar = useCallback((l: LecturaGuardada) => {
    setEstado({ tipo: "lista", texto: l.texto, lang: l.lang, disclaimer: l.disclaimer });
  }, []);

  const reiniciar = useCallback(() => setEstado({ tipo: "nada" }), []);

  return { estado, pedir, mostrar, reiniciar };
}
