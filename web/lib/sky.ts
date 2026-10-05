import type { MajorPhase, Phase } from "@/content/cielo";

import type { BodyKey, Positions } from "./ephemeris";
import { API_URL } from "./config";

// El cielo lo calcula el backend con Swiss Ephemeris, el mismo motor con el que
// se arman las cartas. El pedido se hace desde el servidor de Next, no desde el
// navegador: así no hace falta CORS, el backend recibe una petición por
// revalidación en vez de una por visitante, y la rueda llega en el HTML.
//
// Si el backend no responde, la portada no se cae: el cliente calcula con
// elementos orbitales (lib/ephemeris.ts), que para un dibujo de 400 píxeles es
// indistinguible.
//
// EXCEPCIÓN a `rutasApiSinFetchDirecto.test.ts`: no pasa por `callApi`.
// `callApi` fuerza `cache: "no-store"`, que en la guía de `fetch`
// (`node_modules/next/dist/docs/01-app/03-api-reference/04-functions/fetch.md`,
// "Good to know") es una opción que entra en conflicto con `next.revalidate`
// —Next ignora las dos y tira un warning en desarrollo— así que perdería el
// único pedido por minuto que sostiene el comentario de arriba a cambio de
// uno por visita. El endpoint sí tiene techo por IP en el backend
// (`throttle_scope = "sky"`, 240/hora), pero ese techo ya lo cuida la caché:
// deduplicada a como mucho un pedido por minuto, nunca se acerca. Reenviar la
// IP de quien disparó esa revalidación además no tendría sentido: no es su
// pedido, es el de cualquiera que haya llegado en ese minuto.

const REVALIDATE_SECONDS = 60;
const TIMEOUT_MS = 3000;

type ApiBody = {
  name: string;
  sign: string;
  longitude: number;
  retrograde: boolean;
};

/** Un cuerpo tal como lo da el backend, con el nombre en inglés: es la clave
 *  de `PLANET_NAME_BY_KEY` y `PLANET_GLYPHS`. Incluye a Plutón, que la rueda no
 *  dibuja pero «el cielo de hoy» sí lista. */
export type SkyBody = {
  name: string;
  longitude: number;
  retrograde: boolean;
};

export type Sky = {
  moment: string;
  positions: Positions;
  bodies: SkyBody[];
};

/** El backend nombra los cuerpos en inglés y capitalizados. */
const KEY_BY_NAME: Record<string, BodyKey> = {
  Sun: "sun",
  Moon: "moon",
  Mercury: "mercury",
  Venus: "venus",
  Mars: "mars",
  Jupiter: "jupiter",
  Saturn: "saturn",
  Uranus: "uranus",
  Neptune: "neptune",
};

export async function fetchSky(): Promise<Sky | null> {
  try {
    const res = await fetch(`${API_URL}/api/sky/`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;

    const data: { moment: string; bodies: ApiBody[] } = await res.json();
    const positions = {} as Positions;
    for (const body of data.bodies) {
      const key = KEY_BY_NAME[body.name];
      if (key) positions[key] = body.longitude;
    }

    // Plutón no entra en la rueda; si falta cualquiera de los otros, el dibujo
    // saldría incompleto y es preferible el cálculo local.
    if (Object.keys(positions).length !== Object.keys(KEY_BY_NAME).length) return null;

    const bodies = data.bodies.map(({ name, longitude, retrograde }) => ({ name, longitude, retrograde }));
    return { moment: data.moment, positions, bodies };
  } catch {
    // Backend caído, lento o mal configurado: la portada sigue funcionando.
    return null;
  }
}

/** Las abreviaturas de signo de kerykeion, en el orden del zodíaco: el índice
 *  es el de `SIGN_NAMES`. */
const KERYKEION_SIGNS = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir",
                         "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"];

export type Moon = {
  moment: string;
  phase: Phase;
  illumination: number;
  waxing: boolean;
  nextPhases: { phase: MajorPhase; moment: string }[];
  /** El índice del signo en el que entra, para `SIGN_NAMES`. */
  nextSignIndex: number;
  nextSignMoment: string;
};

/** La Luna de este minuto, de `/api/sky/moon/`.
 *
 * Mismo trato que `fetchSky`, y por la misma razón queda fuera de `callApi`:
 * un pedido por minuto con caché de Next. Si el backend no contesta, la página
 * sale sin el bloque de fases en vez de caerse. */
export async function fetchMoon(): Promise<Moon | null> {
  try {
    const res = await fetch(`${API_URL}/api/sky/moon/`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;

    const data: {
      moment: string;
      phase: Phase;
      illumination: number;
      waxing: boolean;
      next_phases: { phase: MajorPhase; moment: string }[];
      next_sign_change: { sign: string; moment: string };
    } = await res.json();

    const nextSignIndex = KERYKEION_SIGNS.indexOf(data.next_sign_change.sign);
    if (nextSignIndex < 0) return null;

    return {
      moment: data.moment,
      phase: data.phase,
      illumination: data.illumination,
      waxing: data.waxing,
      nextPhases: data.next_phases,
      nextSignIndex,
      nextSignMoment: data.next_sign_change.moment,
    };
  } catch {
    return null;
  }
}
