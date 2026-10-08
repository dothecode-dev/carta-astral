"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { CartaDibujable } from "@/lib/chart";
import type { DatosCarta } from "@/lib/datosCarta";
import type { Locale } from "@/lib/i18n";
import { guardarLectura, type LecturaGuardada } from "@/lib/lecturaLocal";
import { track } from "@/lib/telemetry";

// El pedido de la lectura breve sin cuenta y la espera (spec 2026-10-08,
// RF12, RF16, y §11 v3). La consulta va con backoff y corta a los 5 min —una
// red de seguridad: el fin normal lo decide el latido del backend—; un
// «ocupado» se reintenta solo, sin que la persona haga nada.
//
// Vive en `components/` y no en `lib/` porque corre en el NAVEGADOR y le pega
// a `/api/lectura-anonima`, la ruta de Next, no al backend: la guardia de
// `rutasApiSinFetchDirecto.test.ts` sólo mira `lib/` y `app/api`.

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
const CORTE_MS = 300_000;
const REINTENTO_OCUPADO_MS = 5000;
const REINTENTOS_OCUPADO = 3;

type Motivo = "modelo" | "ip" | "cupo" | "ocupado" | "mantenimiento" | "timeout";

/** Un pedido de lectura, con TODO lo que necesita para terminar solo: la carta
 *  y los datos con que se pidió quedan acá adentro, no en el estado de la
 *  pantalla. Así, si la persona vuelve al formulario mientras se escribe, la
 *  espera sigue «de fondo» y guarda la lectura con SU carta, no con la que esté
 *  en pantalla en ese momento (final review I1). */
type Pedido = {
  /** El id que viaja al backend: sólo se acepta una lectura con este id (C1). */
  id: string;
  cuerpo: object;
  carta: CartaDibujable;
  lang: Locale;
  timer: ReturnType<typeof setTimeout> | null;
};

export function useLecturaAnonima() {
  const [estado, setEstado] = useState<EstadoLectura>({ tipo: "nada" });
  // Cuántas lecturas se guardaron en este navegador desde que se montó: quien
  // muestra «Ver tu lectura de …» la mira para releer el storage.
  const [guardadas, setGuardadas] = useState(0);
  const vivo = useRef(true);
  // El pedido que PINTA la pantalla. Todo lo que vuelve (un timer, un `fetch`
  // en vuelo) compara su pedido con éste: si ya no es el actual, sigue de
  // fondo y no toca el estado. Sin esto, la lectura de una persona podía
  // aparecer sobre la carta de otra.
  const actual = useRef<Pedido | null>(null);
  // Los pedidos con algo pendiente (de frente o de fondo), para cortarlos al
  // desmontar.
  const vivos = useRef(new Set<Pedido>());
  // El último pedido de frente que terminó en «fallida» (modelo, corte u
  // ocupado): «Probar de nuevo» con la MISMA carta lo reusa, así el backend
  // sigue esperándolo, lo relanza o entrega la lista que ya tenga (§11, RF7).
  const reintentable = useRef<{ id: string; carta: CartaDibujable } | null>(null);
  // Las dos funciones se llaman a sí mismas desde un timer: la referencia
  // evita que una `useCallback` se nombre dentro de su propia definición.
  const consultarRef = useRef<(p: Pedido, intento: number, limite: number) => void>(() => {});
  const pedirRef = useRef<(p: Pedido, reintento: number) => Promise<void>>(async () => {});

  useEffect(() => {
    vivo.current = true;
    const pendientes = vivos.current;
    return () => {
      vivo.current = false;
      for (const p of pendientes) if (p.timer) clearTimeout(p.timer);
      pendientes.clear();
    };
  }, []);

  const deFrente = (p: Pedido) => vivo.current && actual.current === p;

  const terminar = useCallback((p: Pedido) => {
    if (p.timer) clearTimeout(p.timer);
    p.timer = null;
    vivos.current.delete(p);
    if (actual.current === p) actual.current = null;
  }, []);

  /** Termina el pedido; si sigue de frente, además muestra cómo terminó. */
  const fallar = useCallback(
    (p: Pedido, motivo: Motivo, siguiente: EstadoLectura = { tipo: "fallida" }) => {
      const pinta = deFrente(p);
      terminar(p);
      track("lectura_anonima_fallida", { motivo });
      if (pinta && siguiente.tipo === "fallida") reintentable.current = { id: p.id, carta: p.carta };
      if (pinta) setEstado(siguiente);
    },
    [terminar],
  );

  const consultar = useCallback(
    (p: Pedido, intento: number, limite: number, ya = false) => {
      // La espera nunca pasa del corte: sin el tope, el último sondeo caía
      // hasta 4 s después del límite y el aviso llegaba tarde. `ya` es la
      // lectura que el backend dice tener escrita: se busca sin esperar.
      const espera = ya ? 0 : Math.min(
        ESPERAS_MS[intento] ?? ESPERA_MAX_MS,
        Math.max(0, limite + 1 - Date.now()),
      );
      if (p.timer) clearTimeout(p.timer);
      p.timer = setTimeout(async () => {
        p.timer = null;
        if (!vivo.current) return;
        if (Date.now() > limite) return fallar(p, "timeout");
        try {
          const r = await fetch("/api/lectura-anonima");
          const cuerpo = (await r.json()) as {
            estado?: string; texto?: string; lang?: Locale; disclaimer?: string; pedido?: string;
          };
          if (!vivo.current) return;
          if (r.ok && cuerpo.pedido !== p.id) {
            // Lo que hay en el servidor es de OTRO pedido (otra carta en este
            // navegador): nunca se muestra ni se guarda como de ésta.
            const pinta = deFrente(p);
            terminar(p);
            if (pinta) {
              track("lectura_anonima_usada", {});
              setEstado({ tipo: "usada" });
            }
            return;
          }
          if (r.ok && cuerpo.estado === "lista" && cuerpo.texto && cuerpo.lang) {
            const lista = { texto: cuerpo.texto, lang: cuerpo.lang, disclaimer: cuerpo.disclaimer ?? "" };
            const pinta = deFrente(p);
            terminar(p);
            guardarLectura({ carta: p.carta, datos: p.cuerpo as DatosCarta, ...lista });
            track("lectura_anonima_generada", {});
            setGuardadas((n) => n + 1);
            if (pinta) setEstado({ tipo: "lista", ...lista });
            return;
          }
          if (r.ok && cuerpo.estado === "fallida") return fallar(p, "modelo");
          if (!r.ok) return fallar(p, "modelo");
          consultarRef.current(p, intento + 1, limite);
        } catch {
          if (!vivo.current) return;
          consultarRef.current(p, intento + 1, limite);
        }
      }, espera);
    },
    [fallar, terminar],
  );

  const enviar = useCallback(
    async (p: Pedido, reintento: number): Promise<void> => {
      if (deFrente(p)) setEstado({ tipo: "esperando", ocupado: reintento > 0 });
      let r: Response;
      try {
        r = await fetch("/api/lectura-anonima", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...p.cuerpo, lang: p.lang, pedido: p.id }),
        });
      } catch {
        if (!vivo.current) return;
        return fallar(p, "modelo");
      }
      if (!vivo.current) return;
      // Un 202 se espera igual aunque la persona ya haya vuelto atrás: la
      // lectura gratis se está escribiendo y se guarda de fondo.
      // `lista` es la de ESTE pedido, escrita y sin acusar (§11, RF7): la
      // entrega el GET.
      if (r.status === 202) {
        const { estado } = (await r.json().catch(() => ({}))) as { estado?: string };
        if (!vivo.current) return;
        return consultar(p, 0, Date.now() + CORTE_MS, estado === "lista");
      }
      const { motivo } = (await r.json().catch(() => ({}))) as { motivo?: string };
      if (!vivo.current) return;
      if (!deFrente(p)) {
        // Volvió atrás antes de que se escribiera nada: no se gastó la lectura
        // y no hay a quién avisarle.
        terminar(p);
        return;
      }
      if (r.status === 409) {
        terminar(p);
        track("lectura_anonima_usada", {});
        return setEstado({ tipo: "usada" });
      }
      if (r.status === 429) return fallar(p, "ip", { tipo: "sin_cupo" });
      if (motivo === "cupo") return fallar(p, "cupo", { tipo: "sin_cupo" });
      if (motivo === "mantenimiento") return fallar(p, "mantenimiento", { tipo: "mantenimiento" });
      if (motivo === "ocupado") {
        if (reintento >= REINTENTOS_OCUPADO) return fallar(p, "ocupado");
        setEstado({ tipo: "esperando", ocupado: true });
        if (p.timer) clearTimeout(p.timer);
        p.timer = setTimeout(() => {
          p.timer = null;
          if (!vivo.current) return;
          // Un «ocupado» no gastó nada: si ya volvió atrás, no se reintenta.
          if (!deFrente(p)) return terminar(p);
          void pedirRef.current(p, reintento + 1);
        }, REINTENTO_OCUPADO_MS);
        return;
      }
      fallar(p, "modelo");
    },
    [consultar, fallar, terminar],
  );

  const pedir = useCallback(
    async (cuerpo: object, carta: CartaDibujable, lang: Locale): Promise<void> => {
      // Un pedido de frente sigue en curso (un doble clic): no se abre otro,
      // que el backend rechazaría como de otra carta.
      if (actual.current) return;
      const previo = reintentable.current;
      reintentable.current = null;
      const id = previo && previo.carta === carta ? previo.id : crypto.randomUUID();
      const p: Pedido = { id, cuerpo, carta, lang, timer: null };
      actual.current = p;
      vivos.current.add(p);
      track("lectura_anonima_pedida", {});
      return enviar(p, 0);
    },
    [enviar],
  );

  useEffect(() => {
    consultarRef.current = consultar;
    pedirRef.current = enviar;
  }, [consultar, enviar]);

  /** Lo que estaba de frente pasa a fondo: deja de pintar, pero si ya se está
   *  escribiendo, termina y se guarda con su carta. */
  const soltar = useCallback(() => {
    actual.current = null;
  }, []);

  const mostrar = useCallback((l: LecturaGuardada) => {
    soltar();
    setEstado({ tipo: "lista", texto: l.texto, lang: l.lang, disclaimer: l.disclaimer });
  }, [soltar]);

  const reiniciar = useCallback(() => {
    soltar();
    setEstado({ tipo: "nada" });
  }, [soltar]);

  return { estado, pedir, mostrar, reiniciar, guardadas };
}
