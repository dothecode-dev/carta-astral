"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";

import { SolarSystem } from "@/components/SolarSystem";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

// El botón que gasta el crédito, y la espera mientras se escribe el informe.
//
// El informe tiene ocho secciones (RF1) y el backend las escribe en un hilo
// aparte (RF10): el POST devuelve 202 al instante y esto sondea
// `interpretation/estado` hasta que están todas. Tarda unos seis minutos:
// ocho llamadas secuenciales de hasta 1000 palabras cada una
// (`informe_service.py`, docstring de `generar_informe`).

/** Cada cuánto se pregunta cuánto avanzó el informe mientras se escribe. */
export const POLL_MS = 5000;
/**
 * Tope de esa espera, en consultas: once minutos.
 *
 * El informe tarda ~6; el tope viejo (24 intentos × 5 s = 2 minutos) se
 * quedaba corto y la web se rendía en medio de una generación normal.
 */
export const POLL_TRIES = 132;

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

type Estado = { completa: boolean; hechas: number; total: number };

/**
 * Si ya se reintentó el POST de recuperación (HALLAZGO 3) para esta carta e
 * idioma en esta pestaña. `sessionStorage` —no una variable en memoria— para
 * que sobreviva a la recarga completa que da lugar al reintento: es
 * exactamente el caso que hay que frenar en la SEGUNDA recarga en adelante.
 *
 * Envuelto en try/catch porque un navegador en modo privado puede bloquear
 * `sessionStorage`: en ese caso, el peor resultado es reintentar el POST en
 * cada recarga, que sigue siendo seguro (no cobra dos veces), sólo menos
 * prolijo con la cuota diaria de la ruta.
 */
function yaReintentoEstaSesion(chartId: string, locale: string): boolean {
  try {
    return window.sessionStorage.getItem(`astra:retomo:${chartId}:${locale}`) === "1";
  } catch {
    return false;
  }
}

function marcarReintentado(chartId: string, locale: string): void {
  try {
    window.sessionStorage.setItem(`astra:retomo:${chartId}:${locale}`, "1");
  } catch {
    // ver comentario de yaReintentoEstaSesion
  }
}

export function ChartActions({
  locale,
  chartId,
  langs,
  timeKnown,
  dict,
}: {
  locale: Locale;
  chartId: string;
  langs: string[];
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

  const yaLeida = langs.includes(locale);
  // Si ya existe en otro idioma, traducirla no cuesta: el backend no vuelve a
  // cobrar. Decir "usa 1 crédito" ahí sería mentir, y es lo que hace la app.
  const enOtroIdioma = !yaLeida && langs.length > 0;

  /**
   * Sondea cuántas de las ocho secciones ya están escritas, hasta que el
   * informe está completo.
   *
   * El POST sólo arranca la generación (RF10): responde 202 y el texto real
   * tarda varios minutos en un hilo de fondo. Sin este sondeo la web no
   * tendría forma de saber cuándo terminó, ni nada real que mostrar mientras
   * tanto.
   *
   * `fetch` rechaza ante un corte de red — no resuelve con `ok: false` — y en
   * una espera de hasta once minutos un wifi que parpadea o una laptop que
   * suspende y despierta son cosa de todos los días. Sin el `try/catch`, esa
   * excepción aborta el bucle entero y deja el sistema solar girando para
   * siempre: acá se cuenta como un intento fallido más, no como el fin de la
   * espera — la generación sigue corriendo en el servidor aunque esta
   * consulta puntual no haya llegado.
   */
  const waitForReading = useCallback(async (): Promise<boolean> => {
    for (let intento = 0; intento < POLL_TRIES; intento++) {
      await sleep(POLL_MS);
      try {
        const res = await fetch(`/api/charts/${chartId}/interpretation/estado?lang=${locale}`);
        if (!res.ok) continue;
        const estado = (await res.json()) as Estado;
        setProgreso({ hechas: estado.hechas, total: estado.total });
        if (estado.completa) return true;
      } catch (err) {
        console.error(`sondeo del informe ${chartId}: falló la consulta`, err);
      }
    }
    return false;
  }, [chartId, locale]);

  /** Espera el resto del informe y, si termina, trae la lectura a la página. */
  const seguirGenerando = useCallback(
    async (contarEvento: boolean) => {
      if (!(await waitForReading())) {
        setBusy(false);
        setError(dict.chart.failed);
        return;
      }

      // Sin este flag, retomar una generación ajena tras recargar la pestaña
      // (ver el efecto de más abajo) contaría el mismo evento dos veces: el
      // costo por lectura se mide una vez por generación, no por pestaña.
      if (contarEvento) track("interpretacion_generada", { lang: locale });

      // La lectura queda debajo de la carta, en esta misma página. La
      // animación sigue hasta que el refresh trae el texto, no hasta que el
      // informe está.
      startTransition(() => router.refresh());
      setBusy(false);
    },
    [dict.chart.failed, locale, router, startTransition, waitForReading],
  );

  // Si la pestaña se recarga a mitad de un informe, este componente vuelve a
  // montar de cero y no tiene memoria de que ya lo pidió: sin este efecto
  // mostraría el botón "Leer mi carta" como si nada estuviera pasando,
  // aunque el backend siga escribiendo. Volver a apretarlo sería inofensivo
  // (`iniciar_generacion` no cobra dos veces y el segundo hilo se retira si
  // el lock de la carta ya está tomado) pero la experiencia es "se perdió".
  //
  // `hechas > 0` sin `completa` es la única prueba inequívoca de que hay una
  // generación en curso. `hechas === 0` es ambiguo —una fila recién creada
  // pega la misma respuesta que "nunca se pidió nada"— y se trata como
  // "nada en curso": es la lectura segura, porque el peor caso es el mismo
  // reintento inofensivo de arriba.
  useEffect(() => {
    if (yaLeida) return;
    let cancelado = false;

    (async () => {
      try {
        const res = await fetch(`/api/charts/${chartId}/interpretation/estado?lang=${locale}`);
        if (!res.ok || cancelado) return;
        const estado = (await res.json()) as Estado;
        if (cancelado || estado.completa || estado.hechas <= 0) return;

        setProgreso({ hechas: estado.hechas, total: estado.total });
        setBusy(true);

        // HALLAZGO 3: si el proceso que generaba murió (deploy, worker
        // reciclado, fallo) no queda nada corriendo del lado del servidor, y
        // sondear sin volver a pedirlo deja el progreso congelado hasta el
        // tope de `POLL_TRIES`. `iniciar_generacion` no cobra dos veces
        // cuando la fila ya existe (backend/api/interpretation_service.py):
        // este POST es seguro. Una sola vez por pestaña alcanza — si el
        // proceso sigue vivo, el backend lo ignora porque el lock de la carta
        // ya está tomado; repetirlo en cada recarga sólo gastaría la cuota
        // diaria de la ruta sin necesidad.
        //
        // No puede chocar con el 409 del HALLAZGO 2 (esta carta en OTRO
        // idioma en curso): ese código sólo lo lanza `iniciar_generacion` al
        // CREAR una fila nueva, y acá la fila de este mismo idioma ya existe
        // (por eso `hechas > 0`), así que el backend la devuelve tal cual sin
        // volver a cobrar ni a chequear siblings.
        if (!cancelado && !yaReintentoEstaSesion(chartId, locale)) {
          marcarReintentado(chartId, locale);
          try {
            await fetch(`/api/charts/${chartId}/interpretation`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ lang: locale }),
            });
          } catch (err) {
            // Un corte de red acá no es el fin: si el proceso seguía vivo, el
            // sondeo de abajo lo encuentra igual.
            console.error(`reintento del informe ${chartId} falló`, err);
          }
        }

        if (!cancelado) await seguirGenerando(false);
      } catch (err) {
        // Si esta consulta falla, se muestra el botón: reintentar
        // clickeando es inofensivo.
        console.error(`consulta de arranque del informe ${chartId} falló`, err);
      }
    })();

    return () => {
      cancelado = true;
    };
  }, [chartId, locale, yaLeida, seguirGenerando]);

  async function interpret() {
    setProgreso(null);
    setBusy(true);
    setError(null);

    let res: Response;
    try {
      res = await fetch(`/api/charts/${chartId}/interpretation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: locale }),
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
      // HALLAZGO 2: el backend responde 409 cuando ya hay una generación en
      // curso para esta carta en OTRO idioma (`_sibling_en_curso` en
      // backend/api/interpretation_service.py: pedir "es" y, a mitad de su
      // generación, pedir "en" cae acá). No es un fallo duro — es "esperá
      // unos segundos y reintentá" — así que no comparte mensaje con
      // `dict.chart.failed`.
      //
      // Elegido: mensaje específico + dejar el botón (mismo patrón que 402 y
      // 503, arriba). La alternativa —enganchar el sondeo de `estado` para
      // este idioma— no sirve acá: el backend borra la fila de ESTE idioma
      // antes de devolver el 409 (`interpretacion.delete()` en
      // `iniciar_generacion`), así que `estado` respondería `hechas: 0` como
      // si nunca se hubiera pedido nada, indistinguible del caso "no hay
      // nada en curso". Sondear ahí sería fingir un progreso que no existe.
      if (res.status === 409) {
        setError(dict.chart.generationInProgress);
      } else {
        setError(res.status === 402 ? dict.chart.noCredits : dict.chart.failed);
      }
      return;
    }

    // El POST arrancó el hilo de fondo y respondió 202: la lectura todavía no
    // existe. Si el sondeo se agota, se avisa y se deja reintentar (RF7): un
    // botón que desaparece para siempre sería peor que un informe tardío.
    await seguirGenerando(true);
  }

  if (busy || refrescando) {
    return (
      <section className="waiting">
        <SolarSystem size={200} speed={2.5} />
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
              : dict.chart.waitBody}
          </p>
        </div>
      </section>
    );
  }

  if (yaLeida) return null;

  return (
    <div className="chartActions">
      <button type="button" className="btn btnPrimary" onClick={interpret}>
        {dict.chart.interpret}
      </button>
      <p className="fieldNote">
        {enOtroIdioma ? dict.chart.interpretFreeLang : dict.chart.interpretCost}
      </p>
      {!timeKnown && <p className="fieldNote">{dict.chart.noTimeWarning}</p>}
      {error && (
        <p className="formError" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
