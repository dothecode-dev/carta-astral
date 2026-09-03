"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import { cantidad, puede, type Derecho } from "@/lib/derechos";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

// Los dos botones de la carta, y la espera mientras se escribe el producto
// elegido.
//
// Hay dos productos por carta (RF1, RF2): una lectura breve gratis (tier
// "corto", la paga un derecho de `lectura_breve`) y un informe completo de
// ocho secciones a US$ 29 (tier "largo", lo paga un derecho de
// `informe_natal`). Conviven: leer la breve no consume ni bloquea el
// completo, y al revés.
//
// El backend las escribe en un hilo aparte (RF10): el POST devuelve 202 al
// instante y esto sondea `interpretation/estado` hasta que están todas. El
// completo tarda unos seis minutos (ocho llamadas secuenciales de hasta 1000
// palabras cada una, `informe_service.py`); la breve, una sola sección.

/** Cada cuánto se pregunta cuánto avanzó el informe mientras se escribe. */
export const POLL_MS = 5000;
/**
 * Tope de esa espera, en consultas: once minutos.
 *
 * El informe completo tarda ~6; el tope viejo (24 intentos × 5 s = 2 minutos)
 * se quedaba corto y la web se rendía en medio de una generación normal.
 */
export const POLL_TRIES = 132;

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

type Tier = "corto" | "largo";

type Estado = { completa: boolean; hechas: number; total: number };

/**
 * Qué tier se pidió para esta carta e idioma en esta pestaña, si alguno.
 *
 * `sessionStorage` —no una variable en memoria— para que sobreviva a la
 * recarga completa que da lugar al reintento (HALLAZGO 3): es exactamente el
 * caso que hay que cubrir. Guardar el TIER acá, no sólo un booleano, es lo
 * que evita el bug caro (RF24): sin esto, una recarga a mitad de la lectura
 * breve gratis no tendría forma de saber que lo que hay que retomar es la
 * breve, y adivinar "largo" cobraría el informe de US$ 29 que nadie pidió.
 *
 * Se escribe al hacer el click que arranca la generación (`interpret`), no
 * al reintentar: para cuando el efecto de recuperación la necesita, ya tiene
 * que estar.
 *
 * Envuelto en try/catch porque un navegador en modo privado puede bloquear
 * `sessionStorage`: en ese caso, el peor resultado es que una recarga a
 * mitad de una generación no se recupere sola y vuelva a mostrar los
 * botones — no que cobre el producto equivocado.
 */
function tierPedido(chartId: string, locale: string): Tier | null {
  try {
    const v = window.sessionStorage.getItem(`interpret:${chartId}:${locale}`);
    return v === "corto" || v === "largo" ? v : null;
  } catch {
    return null;
  }
}

function recordarTier(chartId: string, locale: string, tier: Tier): void {
  try {
    window.sessionStorage.setItem(`interpret:${chartId}:${locale}`, tier);
  } catch {
    // ver comentario de tierPedido
  }
}

/**
 * Si ya se reintentó el POST de recuperación (HALLAZGO 3) para este tier de
 * esta carta e idioma en esta pestaña. Sin este freno, cada recarga mientras
 * el proceso murió dispararía un POST nuevo: inofensivo para el derecho
 * (`iniciar_generacion` no cobra dos veces), pero gasta sin necesidad la
 * cuota diaria de la ruta.
 *
 * Con el tier en la clave: la breve y el completo pueden generarse en la
 * misma pestaña (uno detrás del otro), y sin distinguirlos acá, reintentar
 * la breve marcaría también "ya reintentado" al completo — si el proceso del
 * completo muriera después, esta red de seguridad no se activaría para él.
 */
function yaReintentoEstaSesion(chartId: string, locale: string, tier: Tier): boolean {
  try {
    return window.sessionStorage.getItem(`astra:retomo:${chartId}:${locale}:${tier}`) === "1";
  } catch {
    return false;
  }
}

function marcarReintentado(chartId: string, locale: string, tier: Tier): void {
  try {
    window.sessionStorage.setItem(`astra:retomo:${chartId}:${locale}:${tier}`, "1");
  } catch {
    // ver comentario de yaReintentoEstaSesion
  }
}

export function ChartActions({
  locale,
  chartId,
  interpretations,
  enCurso,
  derechos,
  timeKnown,
  dict,
}: {
  locale: Locale;
  chartId: string;
  /** Por idioma, qué tiers están completos. Sólo trae los idiomas con al
   *  menos uno listo — un idioma sin nada no aparece con lista vacía. */
  interpretations: Record<string, Tier[]>;
  /**
   * Por idioma, qué tiers se están escribiendo AHORA (`en_curso` del payload
   * de la carta). Lo dice el servidor mirando que el lock de generación siga
   * vivo, así que es más confiable que `sessionStorage`: ese muere al cerrar
   * la pestaña y no sirve para "cierro y vuelvo mañana".
   */
  enCurso: Record<string, Tier[]>;
  /**
   * Derechos de la cuenta (`GET /api/account/`). De acá salen tanto si la
   * breve está habilitada (`puede(derechos, "leer_breve")`) como cuántas
   * quedan, para la nota bajo el botón.
   *
   * El botón del completo no usa esto para habilitarse ni deshabilitarse —
   * a diferencia de la breve, siempre queda clickeable, y si no hay derecho
   * de `leer_informe` el 402 (`code: "sin_leer_informe"`) es quien lo dice.
   */
  derechos: Derecho[];
  /** RF12: si la carta no tiene hora, el informe sale sin la sección de casas. */
  timeKnown: boolean;
  dict: Dict;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  // `router.refresh()` no avisa cuándo terminó. Envuelto en una transición,
  // `refrescando` dice cuándo el servidor ya devolvió la lectura: sin eso la
  // animación se quedaba encendida para siempre debajo del texto ya escrito.
  const [refrescando, startTransition] = useTransition();
  const [progreso, setProgreso] = useState<{ hechas: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Qué tier se está esperando ahora mismo. Sólo importa para elegir el
  // texto de espera (`waitBody` vs `waitBodyBreve`) en los ~5 segundos antes
  // del primer sondeo, cuando `progreso` todavía es `null` y no hay otra
  // forma de saber si se está escribiendo un informe de ocho secciones o una
  // sola lectura breve.
  const [tierEnCurso, setTierEnCurso] = useState<Tier | null>(null);

  const tiersAqui = interpretations[locale] ?? [];
  const tieneBreve = tiersAqui.includes("corto");
  const tieneCompleto = tiersAqui.includes("largo");

  /**
   * Si `tier` ya está completo en algún OTRO idioma de esta carta. El
   * backend traduce una lectura ya escrita sin tocar el ledger (no cobra de
   * nuevo): decir el precio o "te quedan {n}" en ese caso sería mentir, así
   * que la nota del botón cambia a `interpretFreeLang`.
   */
  function enOtroIdioma(tier: Tier): boolean {
    return Object.entries(interpretations).some(
      ([lang, tiers]) => lang !== locale && tiers.includes(tier),
    );
  }

  /**
   * Sondea cuántas de las secciones de `tier` ya están escritas, hasta que
   * ese producto está completo. La breve tiene una sola sección (`total`
   * pasa a ser 1, no 8); el completo, ocho.
   *
   * `fetch` rechaza ante un corte de red — no resuelve con `ok: false` — y en
   * una espera de hasta once minutos un wifi que parpadea o una laptop que
   * suspende y despierta son cosa de todos los días. Sin el `try/catch`, esa
   * excepción aborta el bucle entero y deja el sistema solar girando para
   * siempre: acá se cuenta como un intento fallido más, no como el fin de la
   * espera.
   */
  const waitForReading = useCallback(
    async (tier: Tier): Promise<boolean> => {
      for (let intento = 0; intento < POLL_TRIES; intento++) {
        await sleep(POLL_MS);
        try {
          const res = await fetch(
            `/api/charts/${chartId}/interpretation/estado?lang=${locale}&tier=${tier}`,
          );
          if (!res.ok) continue;
          const estado = (await res.json()) as Estado;
          setProgreso({ hechas: estado.hechas, total: estado.total });
          if (estado.completa) return true;
        } catch (err) {
          console.error(`sondeo del informe ${chartId}: falló la consulta`, err);
        }
      }
      return false;
    },
    [chartId, locale],
  );

  /** Espera el resto de `tier` y, si termina, trae la lectura a la página. */
  const seguirGenerando = useCallback(
    async (contarEvento: boolean, tier: Tier) => {
      if (!(await waitForReading(tier))) {
        setBusy(false);
        setError(dict.chart.failed);
        return;
      }

      // Sin este flag, retomar una generación ajena tras recargar la pestaña
      // (ver el efecto de más abajo) contaría el mismo evento dos veces: el
      // costo por lectura se mide una vez por generación, no por pestaña.
      if (contarEvento) track("interpretacion_generada", { lang: locale, tier });

      // La lectura queda debajo de la carta, en esta misma página. La
      // animación sigue hasta que el refresh trae el texto, no hasta que el
      // informe está.
      startTransition(() => router.refresh());
      setBusy(false);
    },
    [dict.chart.failed, locale, router, startTransition, waitForReading],
  );

  // Si la pestaña se recarga a mitad de una generación, este componente
  // vuelve a montar de cero y no tiene memoria de que ya la pidió. La única
  // fuente de esa memoria es `sessionStorage` (`tierPedido`): sin un tier ahí,
  // no hay nada que recuperar y se muestran los botones normales — es la
  // lectura segura, porque volver a clickear es inofensivo (`iniciar_generacion`
  // no cobra dos veces y el segundo hilo se retira si el lock ya está tomado).
  //
  // Que `sessionStorage` tenga un tier para esta carta+idioma, y que la carta
  // (`interpretations`, la fuente de verdad del servidor) todavía no lo tenga
  // completo, ES la prueba de que hay algo para recuperar: a diferencia del
  // diseño de un solo producto, acá no hace falta mirar `hechas` para
  // desambiguar, porque la breve tiene una sola sección y jamás pasa por un
  // "hechas > 0 sin completar" observable — sondearla así la dejaría sin red
  // de seguridad ante HALLAZGO 3 (el proceso que muere a mitad de camino).
  useEffect(() => {
    if (tieneBreve && tieneCompleto) return;
    // Lo que el servidor declara en curso manda sobre `sessionStorage`: éste
    // sobrevive un F5 pero muere al cerrar la pestaña, y el caso que importa
    // es volver más tarde. Si hay dos tiers escribiéndose, el completo es el
    // que la persona pagó y el que tarda seis minutos.
    const enCursoAqui = enCurso[locale] ?? [];
    const tierServidor = enCursoAqui.includes("largo")
      ? "largo"
      : (enCursoAqui[0] ?? null);
    const tier = tierServidor ?? tierPedido(chartId, locale);
    if (!tier) return;
    if ((tier === "corto" && tieneBreve) || (tier === "largo" && tieneCompleto)) return;

    let cancelado = false;

    (async () => {
      setBusy(true);
      setTierEnCurso(tier);

      // HALLAZGO 3: si el proceso que generaba murió (deploy, worker
      // reciclado, fallo) no queda nada corriendo del lado del servidor, y
      // sondear sin volver a pedirlo deja el progreso congelado hasta el
      // tope de `POLL_TRIES`. `iniciar_generacion` no cobra dos veces cuando
      // la fila ya existe (backend/api/interpretation_service.py): este POST
      // es seguro. El tier es el que quedó guardado en `sessionStorage` al
      // hacer click, nunca uno adivinado (RF24) — es la clave de este
      // efecto: sin esto, retomar la breve gratis podría reintentar el
      // completo pago.
      //
      // Cuando el tier lo dijo el SERVIDOR, ese reintento sobra: `en_curso`
      // sale de que el lock de generación siga vivo, o sea que hay un hilo
      // escribiendo ahora mismo. Postear ahí sería ruido.
      if (!tierServidor && !yaReintentoEstaSesion(chartId, locale, tier)) {
        marcarReintentado(chartId, locale, tier);
        try {
          await fetch(`/api/charts/${chartId}/interpretation`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lang: locale, tier }),
          });
        } catch (err) {
          // Un corte de red acá no es el fin: el sondeo de abajo lo
          // encuentra igual si el proceso seguía vivo.
          console.error(`reintento del informe ${chartId} falló`, err);
        }
      }

      if (!cancelado) await seguirGenerando(false, tier);
    })();

    return () => {
      cancelado = true;
    };
  }, [chartId, locale, enCurso, tieneBreve, tieneCompleto, seguirGenerando]);

  /**
   * Manda a pagar el informe, con esta carta atada.
   *
   * El backend guarda esa relación (`PasarelaCheckout.chart`) y el webhook la usa
   * para que el informe arranque solo al acreditar el pago: la diferencia
   * entre "pagué y ya se está escribiendo" y "pagué y ahora buscá dónde
   * usarlo".
   */
  async function comprar() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ producto: "informe_natal", chart_id: chartId, locale }),
      });
      if (!res.ok) {
        setBusy(false);
        setError(dict.chart.compraFallo);
        return;
      }
      const { url } = (await res.json()) as { url: string };
      // El checkout de Stripe es otro sitio: no es una navegación de Next.
      window.location.assign(url);
    } catch (err) {
      console.error("no se pudo abrir el checkout", err);
      setBusy(false);
      setError(dict.chart.compraFallo);
    }
  }

  async function interpret(tier: Tier) {
    setProgreso(null);
    setBusy(true);
    setTierEnCurso(tier);
    setError(null);

    // Antes del fetch: si la pestaña se cierra o recarga mientras el POST
    // todavía está en vuelo, el efecto de recuperación de arriba tiene que
    // encontrar el tier igual (RF24).
    recordarTier(chartId, locale, tier);

    let res: Response;
    try {
      res = await fetch(`/api/charts/${chartId}/interpretation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: locale, tier }),
      });
    } catch (err) {
      // Mismo motivo que en `waitForReading`: un corte de red acá no es un
      // rechazo del backend, y sin este catch dejaba la animación encendida
      // para siempre en vez de devolver el botón.
      console.error(`inicio del informe ${chartId} falló`, err);
      setBusy(false);
      setError(dict.chart.failed);
      return;
    }

    if (!res.ok) {
      setBusy(false);
      if (res.status === 409) {
        // HALLAZGO 2: el backend responde 409 cuando ya hay una generación en
        // curso para esta carta en OTRO idioma (`_sibling_en_curso`). No es
        // un fallo duro — es "esperá unos segundos y reintentá".
        setError(dict.chart.generationInProgress);
      } else if (res.status === 402) {
        // El 402 trae `code: "sin_leer_breve" | "sin_leer_informe"` para
        // distinguir quedarse sin el lote gratis de no tener el informe
        // comprado.
        let code: string | undefined;
        try {
          code = ((await res.json()) as { code?: string }).code;
        } catch {
          // cuerpo no parseable: se cae al mensaje genérico de abajo.
        }
        setError(
          code === "sin_leer_breve"
            ? dict.chart.sinLeerBreve
            : code === "sin_leer_informe"
              ? dict.chart.sinLeerInforme
              : dict.chart.sinDerecho,
        );
      } else {
        setError(dict.chart.failed);
      }
      return;
    }

    // El POST arrancó el hilo de fondo y respondió 202: la lectura todavía no
    // existe. Si el sondeo se agota, se avisa y se deja reintentar (RF7).
    await seguirGenerando(true, tier);
  }

  if (busy || refrescando) {
    return (
      <section className="waiting">
        <SolarSystem size={280} speed={2.5} />
        <div className="waitingCopy">
          <h2 className="display waitingTitle">{dict.chart.waitTitle}</h2>
          <p className="waitingBody">
            {progreso
              ? // HALLAZGO 4: `hechas` son las secciones YA terminadas, no la
                // que está en curso — con 0 hechas ya se está escribiendo la
                // sección 1, no la "0". `min` cubre el instante en que
                // `hechas` llega a `total` pero `completa` todavía no se leyó.
                dict.chart.waitProgress
                  .replace("{hechas}", String(Math.min(progreso.hechas + 1, progreso.total)))
                  .replace("{total}", String(progreso.total))
              : // Antes del primer sondeo (`progreso` todavía null, los primeros
                // ~5 segundos de cualquier generación) no hay otra pista de qué
                // se está escribiendo: sin distinguir acá, la breve —una sola
                // llamada al modelo— mostraba "en ocho secciones", que puede
                // ser el único texto que alguien vea en toda esa espera.
                tierEnCurso === "corto"
                  ? dict.chart.waitBodyBreve
                  : dict.chart.waitBody}
          </p>
          {/* Aparte del párrafo de arriba, que a los ~5 segundos pasa a ser el
              progreso: esta frase acompaña los seis minutos enteros. */}
          <p className="waitingColor">{dict.chart.waitColor}</p>
        </div>
      </section>
    );
  }

  // Con el completo ya comprado no queda nada para ofrecer: ni la breve
  // (aunque no se haya leído nunca) ni el completo. La página siempre
  // prioriza el tier largo al elegir qué lectura mostrar (`page.tsx`), así
  // que una breve generada después de esto es contenido que nadie ve nunca
  // — gastar una de las tres lecturas breves de por vida en eso es puro
  // desperdicio.
  if (tieneCompleto) return null;

  const breveDisponibles = cantidad(derechos, "lectura_breve");
  /**
   * Si el informe se puede pedir sin volver a pagar: porque hay derecho, o
   * porque ya está escrito en otro idioma y traducirlo no cuesta.
   *
   * El backend no cobra por traducir una lectura ya escrita
   * (`_sibling_completo` en `interpretation_service.py`), y la nota de abajo
   * ya lo decía —`interpretFreeLang`—, pero el botón mandaba a pagar igual:
   * US$ 29 por algo gratis, con el aviso de que era gratis al lado.
   */
  const puedeLeerlo = puede(derechos, "leer_informe") || enOtroIdioma("largo");
  /** Informes comprados sin usar. Distinto de `puedeLeerlo`, que también es
   *  cierto por una traducción gratis: ahí no hay nada pago que descontar. */
  const informesPagos = cantidad(derechos, "informe_natal");

  return (
    <div className="chartActions">
      <div className="chartActionsRow">
        {!tieneBreve && (
          <div className="chartActionCol">
            <button
              type="button"
              className="btn btnGhost"
              disabled={!puede(derechos, "leer_breve") || busy}
              onClick={() => interpret("corto")}
            >
              {dict.chart.interpretBreve}
            </button>
            <p className="fieldNote">
              {enOtroIdioma("corto")
                ? dict.chart.interpretFreeLang
                : dict.chart.interpretBreveNota.replace("{n}", String(breveDisponibles))}
            </p>
          </div>
        )}
        {!tieneCompleto && (
          <div className="chartActionCol">
            {/* Con derecho se lee; sin derecho se paga. El mismo lugar de la
                pantalla hace las dos cosas porque para quien mira es el mismo
                gesto —"quiero mi informe"—, y cobrarle a quien ya pagó (un
                pack deja cinco) sería cobrarle dos veces lo mismo. */}
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy}
              onClick={() => (puedeLeerlo ? interpret("largo") : comprar())}
            >
              {puedeLeerlo
                ? dict.chart.interpretCompletoConDerecho
                : dict.chart.interpretCompleto}
            </button>
            <p className="fieldNote">
              {enOtroIdioma("largo")
                ? dict.chart.interpretFreeLang
                : // Con derecho no se nombra el precio: el botón dice "Leer" y
                  // decir "US$ 29" abajo hacía parecer que iba a cobrar otra
                  // vez a quien ya había pagado —un pack deja cinco—.
                  informesPagos > 0
                    ? timeKnown
                      ? dict.chart.interpretCompletoNotaConDerecho
                      : dict.chart.interpretCompletoNotaConDerechoSinHora
                    : // RF12: sin hora de nacimiento el informe sale con siete
                      // secciones, sin la de casas (`noTimeWarning`, debajo). Sin
                      // esta rama, el botón prometía "ocho secciones" para
                      // cualquier carta, contradiciendo ese aviso en la misma
                      // pantalla.
                      timeKnown
                      ? dict.chart.interpretCompletoNota
                      : dict.chart.interpretCompletoNotaSinHora}
            </p>
            {/* Sólo con más de uno: con el último, lo que importa es que ya
                está pago, y "te queda 1" no agrega nada. */}
            {informesPagos > 1 && (
              <p className="fieldNote">
                {dict.chart.interpretCompletoSaldo.replace("{n}", String(informesPagos - 1))}
              </p>
            )}
            {/* El pie de la lectura ya no anuncia que la escribe una IA: la
                explicación entera está en los Términos de uso. Acá queda a un
                clic, que es el único lugar donde callarlo sale caro — antes de
                que alguien ponga US$ 29. */}
            <Link className="fieldNote comoSeEscribe" href={`/${locale}/legal/terms`}>
              {dict.chart.comoSeEscribe}
            </Link>
          </div>
        )}
      </div>
      {!timeKnown && <p className="fieldNote">{dict.chart.noTimeWarning}</p>}
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
