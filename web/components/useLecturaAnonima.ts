"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { CartaDibujable } from "@/lib/chart";
import type { DatosCarta } from "@/lib/datosCarta";
import type { Locale } from "@/lib/i18n";
import {
  borrarPedido,
  guardarLectura,
  guardarPedido,
  leerLectura,
  leerPedido,
  type LecturaGuardada,
} from "@/lib/lecturaLocal";
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
  /** Falta en el pedido retomado al montar: ése sólo consulta, no se reenvía. */
  lang?: Locale;
  timer: ReturnType<typeof setTimeout> | null;
};

/** El acuse (§11 v3): la lectura ya está guardada en este navegador y el
 *  backend la puede borrar. Si falla da igual —el vencimiento de 15 min la
 *  borra igual—, así que no se reintenta ni se avisa; el pedido en curso se
 *  borra en los dos casos. Si la pestaña se cierra antes, al volver se retoma,
 *  el GET la vuelve a dar y se guarda y acusa de nuevo. */
async function acusar(pedido: string): Promise<void> {
  try {
    await fetch(`/api/lectura-anonima?${new URLSearchParams({ pedido })}`, { method: "DELETE" });
  } catch {
    // Ignorado a propósito: ver arriba.
  }
  borrarPedido(pedido);
}

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

  /** Corta el pedido. Salvo que lo pida quien llega con la lista (que lo
   *  borra después del acuse), también lo saca del storage: ya no hay nada que
   *  retomar. Sólo si el guardado es ÉSTE: el de otra carta sigue. */
  const terminar = useCallback((p: Pedido, conservarEnCurso = false) => {
    if (p.timer) clearTimeout(p.timer);
    p.timer = null;
    vivos.current.delete(p);
    if (actual.current === p) actual.current = null;
    if (!conservarEnCurso) borrarPedido(p.id);
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
            terminar(p, true);
            guardarLectura({ carta: p.carta, datos: p.cuerpo as DatosCarta, pedido: p.id, ...lista });
            void acusar(p.id);
            track("lectura_anonima_generada", {});
            setGuardadas((n) => n + 1);
            if (pinta) setEstado({ tipo: "lista", ...lista });
            return;
          }
          if (r.ok && cuerpo.estado === "fallida") return fallar(p, "modelo");
          if (r.status === 404) {
            // Otra pestaña que esperaba el MISMO pedido ya la guardó y la
            // acusó, y el servidor la borró: está en el storage compartido.
            // Se muestra ésa; ya la contó la otra, acá no se cuenta de nuevo.
            const otra = leerLectura();
            if (otra?.pedido === p.id) {
              const pinta = deFrente(p);
              terminar(p);
              setGuardadas((n) => n + 1);
              if (pinta) setEstado({ tipo: "lista", texto: otra.texto, lang: otra.lang, disclaimer: otra.disclaimer });
              return;
            }
          }
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
      // La MISMA carta ya se está escribiendo de fondo (tras «Nueva carta» o
      // una recarga): se la vuelve a traer al frente. Un pedido nuevo el
      // backend lo rechazaría como «usada» mientras la lectura sigue llegando.
      const mismos = JSON.stringify(cuerpo);
      for (const v of vivos.current) {
        if (JSON.stringify(v.cuerpo) !== mismos) continue;
        actual.current = v;
        setEstado({ tipo: "esperando", ocupado: false });
        return;
      }
      const previo = reintentable.current;
      reintentable.current = null;
      const id = previo && previo.carta === carta ? previo.id : crypto.randomUUID();
      const p: Pedido = { id, cuerpo, carta, lang, timer: null };
      actual.current = p;
      vivos.current.add(p);
      // Para retomarlo si se recarga. No pisa el de OTRA carta que siga en
      // curso de fondo: éste, de todos modos, el backend lo rechazaría.
      const enCurso = leerPedido();
      if (!enCurso || enCurso.pedido === id) {
        guardarPedido({ pedido: id, carta, datos: cuerpo as DatosCarta });
      }
      track("lectura_anonima_pedida", {});
      return enviar(p, 0);
    },
    [enviar],
  );

  useEffect(() => {
    consultarRef.current = consultar;
    pedirRef.current = enviar;
  }, [consultar, enviar]);

  // Al montar, un pedido en curso guardado (una recarga, otra pestaña) se
  // retoma DE FONDO: nunca pinta, y si llega la lista la guarda con su carta,
  // la acusa y suma a `guardadas` para que aparezca «Ver tu lectura de …».
  // Sin guardia de una sola corrida a propósito: el desmontaje de React en
  // desarrollo vacía `vivos` y corta sus timers, y el segundo montaje lo
  // vuelve a retomar; dos ciclos no quedan nunca.
  useEffect(() => {
    const enCurso = leerPedido();
    if (!enCurso) return;
    for (const v of vivos.current) if (v.id === enCurso.pedido) return;
    const p: Pedido = { id: enCurso.pedido, cuerpo: enCurso.datos, carta: enCurso.carta, timer: null };
    vivos.current.add(p);
    consultar(p, 0, Math.min(enCurso.vence, Date.now() + CORTE_MS), true);
  }, [consultar]);

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
