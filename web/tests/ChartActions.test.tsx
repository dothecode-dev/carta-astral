import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChartActions, POLL_MS, POLL_TRIES } from "@/components/ChartActions";
import { getDict } from "@/lib/i18n";

const refresh = vi.fn();
// Referencia estable a propósito, como el `useRouter()` real: uno nuevo en
// cada llamada rompía el `useCallback` de `seguirGenerando` (depende de
// `router`) y con él el efecto de montaje, que lo tiene como dependencia —
// cada render disparaba el efecto de nuevo, sondeo tras sondeo.
const routerMock = { refresh };
vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));

const dict = getDict("es");
const CHART = "89151d40-e263-4d34-81e0-2fb434f70243";

type Tier = "corto" | "largo";

type DerechoTest = { codigo_producto: string; cantidad_restante: number | null; vigente_hasta: string | null };

function derecho(codigo: string, cantidad: number): DerechoTest {
  return { codigo_producto: codigo, cantidad_restante: cantidad, vigente_hasta: null };
}

function renderActions({
  interpretations = {},
  enCurso = {},
  timeKnown = true,
  freeCredits = 3,
  paidCredits = 1,
}: {
  interpretations?: Record<string, Tier[]>;
  enCurso?: Record<string, Tier[]>;
  timeKnown?: boolean;
  freeCredits?: number;
  paidCredits?: number;
} = {}) {
  return render(
    <ChartActions
      locale="es"
      chartId={CHART}
      timeKnown={timeKnown}
      interpretations={interpretations}
      enCurso={enCurso}
      derechos={[derecho("lectura_breve", freeCredits), derecho("informe_natal", paidCredits)]}
      dict={dict}
    />,
  );
}

/** Respuesta mínima de fetch al POST: `ok`, `status` y, si hace falta, `json`. */
const reply = (status: number, body: unknown = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

/** Respuesta del sondeo de `interpretation/estado`. */
const estado = (completa: boolean, hechas: number, total: number) => ({
  ok: true,
  status: 200,
  json: async () => ({ completa, hechas, total }),
});

beforeEach(() => {
  vi.useFakeTimers();
  refresh.mockClear();
  // El reintento de POST al recargar (HALLAZGO 3) y el tier pedido se
  // recuerdan en sessionStorage por pestaña: sin limpiarlo, un test
  // contamina al siguiente porque todos usan el mismo CHART.
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Avanza el reloj falso dejando que React aplique lo que cambió. */
async function correr(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** Busca el botón por su nombre exacto — hay dos desde que la carta ofrece
 *  dos productos, así que no alcanza con "el botón" a secas. */
async function clickBoton(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
  await correr();
}

describe("ChartActions", () => {
  it("ofrece la lectura breve gratis y, sin derecho, la compra del completo", () => {
    renderActions({ freeCredits: 2, paidCredits: 0 });
    expect(screen.getByRole("button", { name: dict.chart.interpretBreve })).toBeEnabled();
    expect(screen.getByRole("button", { name: dict.chart.interpretCompleto })).toBeEnabled();
  });

  it("manda el tier que se apretó", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(202));
    vi.stubGlobal("fetch", fetchMock);
    renderActions({ freeCredits: 2, paidCredits: 1 });

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.tier).toBe("largo");
  });

  it("sin lecturas gratis deshabilita la breve pero no el completo", () => {
    renderActions({ freeCredits: 0, paidCredits: 1 });
    expect(screen.getByRole("button", { name: dict.chart.interpretBreve })).toBeDisabled();
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeEnabled();
  });

  it("con la breve ya leída sigue ofreciendo el informe completo", () => {
    renderActions({ interpretations: { es: ["corto"] } });
    expect(screen.queryByRole("button", { name: dict.chart.interpretBreve })).toBeNull();
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeEnabled();
  });

  it("no ofrece nada si los dos productos ya están leídos en este idioma", () => {
    const { container } = renderActions({ interpretations: { es: ["corto", "largo"] } });
    expect(container).toBeEmptyDOMElement();
  });

  // La página siempre prioriza el tier largo al elegir qué lectura mostrar
  // (page.tsx): una vez comprado el completo, generar la breve gasta una de
  // las tres lecturas breves de por vida en una lectura que nadie va a ver
  // nunca.
  it("no ofrece la breve para quien ya tiene el completo, aunque nunca la haya leído", () => {
    const { container } = renderActions({ interpretations: { es: ["largo"] } });
    expect(screen.queryByRole("button", { name: dict.chart.interpretBreve })).toBeNull();
    expect(screen.queryByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("una lectura en otro idioma no oculta los botones de este", () => {
    // A diferencia de `interpretation_langs` (deprecado), `interpretations`
    // es por idioma: que "en" tenga los dos tiers no dice nada de "es".
    renderActions({ interpretations: { en: ["corto", "largo"] } });
    expect(screen.getByRole("button", { name: dict.chart.interpretBreve })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeInTheDocument();
  });

  // El backend traduce una lectura ya escrita sin cobrar de nuevo (sin
  // tocar el ledger): la nota del botón no puede seguir diciendo el precio o
  // "te quedan {n}" en ese caso, sería mentir.
  it("si la breve ya existe en otro idioma, la nota avisa que no cuesta", () => {
    renderActions({ interpretations: { en: ["corto"] } });
    const boton = screen.getByRole("button", { name: dict.chart.interpretBreve });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretFreeLang);
  });

  it("si el completo ya existe en otro idioma, la nota avisa que no cuesta", () => {
    renderActions({ interpretations: { en: ["largo"] } });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretFreeLang);
  });

  it("si el completo ya existe en otro idioma, el botón traduce en vez de cobrar", async () => {
    // Sin derecho la pantalla ofrece comprar, pero traducir una lectura ya
    // escrita no cuesta nada del lado del backend: mandar a pagar US$ 29 por
    // eso es cobrar dos veces la misma carta, y la nota de al lado ya venía
    // diciendo que era gratis.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(202)));
    renderActions({ interpretations: { en: ["largo"] }, paidCredits: 0 });

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(fetch).toHaveBeenCalledWith(
      `/api/charts/${CHART}/interpretation`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sin lectura en otro idioma, la nota del completo sigue mostrando el precio", () => {
    renderActions({ interpretations: {}, paidCredits: 0 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompleto });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretCompletoNota);
    expect(boton.parentElement).not.toHaveTextContent(dict.chart.interpretFreeLang);
  });

  it("el 402 distingue quedarse sin gratis de no tener el informe comprado", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(402, { code: "sin_leer_informe" })));
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.sinLeerInforme);
  });

  it("el 402 avisa cuando se acabó el lote de lecturas gratis", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(402, { code: "sin_leer_breve" })));
    renderActions();

    await clickBoton(dict.chart.interpretBreve);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.sinLeerBreve);
  });

  it("un 402 sin code reconocido cae al mensaje genérico", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(402, {})));
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.sinDerecho);
  });

  it("muestra la lectura cuando el informe completo termina", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // el POST arranca la generación en un hilo
      .mockResolvedValue(estado(true, 8, 8)); // el sondeo la encuentra completa
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS);

    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("apaga la espera cuando el informe llega", async () => {
    // La animación quedaba encendida para siempre debajo del texto ya
    // escrito: `router.refresh()` no avisa cuándo termina y nadie apagaba el
    // estado de espera.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(true, 8, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS);

    expect(screen.queryByText(dict.chart.waitTitle)).not.toBeInTheDocument();
    expect(document.querySelector(".waiting")).toBeNull();
  });

  it("mientras genera, muestra la espera", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
  });

  // Los primeros ~5 segundos de cualquier generación, antes del primer
  // sondeo, `progreso` todavía es `null` y se muestra el texto genérico.
  // Para la breve —una sola llamada al modelo— ese puede ser el único texto
  // que alguien vea en toda su primera espera: no puede seguir diciendo
  // "en ocho secciones".
  it("mientras genera la breve, la espera no habla de ocho secciones", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 1));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretBreve);

    expect(screen.getByText(dict.chart.waitBodyBreve)).toBeInTheDocument();
    expect(screen.queryByText(dict.chart.waitBody)).not.toBeInTheDocument();
  });

  it("mientras genera el completo, la espera sigue hablando de las ocho secciones", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByText(dict.chart.waitBody)).toBeInTheDocument();
    expect(screen.queryByText(dict.chart.waitBodyBreve)).not.toBeInTheDocument();
  });

  it("muestra en qué sección va, no una animación ciega", async () => {
    // HALLAZGO 4: `hechas` son las secciones YA terminadas, no la que está en
    // curso. Con 3 hechas, la sección en curso es la 4 (min(hechas+1, total)).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS);

    expect(screen.getByText(/4 de 8/)).toBeInTheDocument();
  });

  it("HALLAZGO 4: arranca en la sección 1, no en la 0", async () => {
    // El primer sondeo llega a los 5 segundos, antes de que termine la
    // sección 1 (`hechas` todavía en 0): mostrar "sección 0 de 8" es mentira,
    // ya está escribiendo la primera.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS);

    expect(screen.getByText(/1 de 8/)).toBeInTheDocument();
    expect(screen.queryByText(/0 de 8/)).not.toBeInTheDocument();
  });

  it("no se rinde a los dos minutos", () => {
    // El informe tarda ~6 minutos: 24 intentos × 5 s (2 minutos) se quedaban cortos.
    expect(POLL_TRIES * POLL_MS).toBeGreaterThanOrEqual(10 * 60 * 1000);
  });

  it("avisa del fallo ante un error del servidor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(503)));
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
  });

  // HALLAZGO 2: el backend devuelve 409 cuando ya hay una generación en curso
  // para esta carta en OTRO idioma (`_sibling_en_curso` en
  // backend/api/interpretation_service.py). No es un fallo duro: es "esperá
  // unos segundos y reintentá". Mostrarlo como `dict.chart.failed` mentía.
  it("avisa que hay una generación en curso ante un 409, y deja reintentar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(409)));
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.generationInProgress);
    // No es un callejón sin salida: el botón sigue ahí para reintentar.
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("se rinde si el informe no aparece completo dentro del tope, y deja reintentar", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS * POLL_TRIES);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
    expect(refresh).not.toHaveBeenCalled();
    // El botón vuelve: no es un callejón sin salida.
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeInTheDocument();
  }, 20000);

  it("avisa que faltará una sección si la carta no tiene hora, antes de cobrar", () => {
    renderActions({ timeKnown: false });
    expect(screen.getByText(/sin hora de nacimiento/i)).toBeInTheDocument();
  });

  it("no avisa de la hora cuando la carta ya la tiene", () => {
    renderActions({ timeKnown: true });
    expect(screen.queryByText(/sin hora de nacimiento/i)).not.toBeInTheDocument();
  });

  // Sin esto, para cualquier carta sin hora la pantalla prometía "ocho
  // secciones" en la nota del botón y admitía, en la misma pantalla, que el
  // informe sale con siete (`noTimeWarning`, debajo).
  it("sin hora de nacimiento, la nota del completo dice siete secciones, no ocho", () => {
    renderActions({ timeKnown: false, paidCredits: 0 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompleto });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretCompletoNotaSinHora);
    expect(boton.parentElement).not.toHaveTextContent(dict.chart.interpretCompletoNota);
  });

  it("con hora de nacimiento, la nota del completo sigue diciendo ocho secciones", () => {
    renderActions({ timeKnown: true, paidCredits: 0 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompleto });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretCompletoNota);
  });

  // El botón ya decía "Leer el informe completo" con un derecho en la cuenta,
  // pero la nota de abajo seguía anunciando "US$ 29 · ocho secciones": a quien
  // había comprado un pack de cinco, la pantalla le mostraba el precio de algo
  // que ya estaba pago, a dos centímetros del botón. Nadie aprieta eso.
  it("con el informe ya comprado, la nota no nombra el precio", () => {
    renderActions({ paidCredits: 1 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho });
    expect(boton.parentElement).toHaveTextContent(dict.chart.interpretCompletoNotaConDerecho);
    expect(boton.parentElement).not.toHaveTextContent(dict.chart.interpretCompletoNota);
  });

  it("sin hora y ya comprado, la nota con derecho también dice siete secciones", () => {
    renderActions({ paidCredits: 1, timeKnown: false });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho });
    expect(boton.parentElement).toHaveTextContent(
      dict.chart.interpretCompletoNotaConDerechoSinHora,
    );
    expect(boton.parentElement).not.toHaveTextContent(dict.chart.interpretCompletoNotaSinHora);
  });

  it("con un pack, dice cuántos quedan después de este", () => {
    renderActions({ paidCredits: 5 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho });
    expect(boton.parentElement).toHaveTextContent(
      dict.chart.interpretCompletoSaldo.replace("{n}", "4"),
    );
  });

  it("con el último informe no habla de saldo: lo que importa es que está pago", () => {
    renderActions({ paidCredits: 1 });
    const boton = screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho });
    expect(boton.parentElement).not.toHaveTextContent("0");
  });

  // `fetch` rechaza ante un corte de red; no resuelve con `ok: false`. En una
  // espera de hasta once minutos eso es cotidiano (wifi que parpadea, la
  // laptop que suspende y despierta), y sin manejarlo la excepción abortaba
  // el bucle entero: el sistema solar quedaba girando para siempre, sin
  // error y sin botón.
  it("un corte de red durante el sondeo no aborta la espera: sigue intentando", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // el POST arranca la generación
      .mockRejectedValueOnce(new TypeError("Failed to fetch")) // el wifi parpadea
      .mockResolvedValue(estado(true, 8, 8)); // vuelve la red y el informe ya está
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);
    await correr(POLL_MS * 2);

    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("avisa del fallo si el POST no llega por un corte de red, y deja reintentar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderActions();

    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeInTheDocument();
  });

  it("si no hay nada que recuperar en esta pestaña, muestra los botones sin llamar al backend", () => {
    // Sin una entrada en sessionStorage para esta carta+idioma, el efecto de
    // montaje no tiene forma segura de saber qué tier sondear (el GET de
    // estado ahora lo exige) — así que no llama a nada y deja los botones.
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderActions();

    expect(screen.getByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("si la pestaña se recarga con un informe completo en curso, retoma el sondeo", async () => {
    sessionStorage.setItem(`interpret:${CHART}:es`, "largo");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // el reintento del POST
      .mockResolvedValue(estado(false, 3, 8)); // los sondeos
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await correr(); // el efecto de montaje dispara el reintento
    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();

    await correr(POLL_MS); // el primer sondeo trae el progreso real
    expect(screen.getByText(/4 de 8/)).toBeInTheDocument();
  });

  // HALLAZGO 3: si el proceso que generaba murió (deploy, worker reciclado,
  // fallo) no hay nada corriendo del lado del servidor tras la recarga.
  // `iniciar_generacion` no cobra dos veces cuando la fila ya existe
  // (backend/api/interpretation_service.py), así que reintentar el POST es
  // seguro.
  it("al recargar con un informe en curso, vuelve a pedir la generación por si el proceso murió", async () => {
    sessionStorage.setItem(`interpret:${CHART}:es`, "largo");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // el reintento del POST
      .mockResolvedValue(estado(false, 3, 8)); // los sondeos siguientes
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await correr();

    const [postUrl, postInit] = fetchMock.mock.calls[0];
    expect(String(postUrl)).toContain(`/api/charts/${CHART}/interpretation`);
    expect(postInit).toMatchObject({ method: "POST" });
  });

  it("no repite el reintento si ya lo hizo antes en esta misma pestaña", async () => {
    // Sin este freno, recargar muchas veces mientras el informe se escribe
    // dispararía un POST por recarga: inofensivo para el derecho, pero gasta
    // sin necesidad la cuota diaria de la ruta (`INTERPRETATION_RATE`) y abre
    // hilos de más en el backend.
    sessionStorage.setItem(`interpret:${CHART}:es`, "largo");
    const primeraTanda = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", primeraTanda);
    const { unmount } = renderActions();
    await correr();
    unmount();

    const segundaTanda = vi.fn().mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", segundaTanda);
    renderActions();
    await correr();

    const posts = segundaTanda.mock.calls.filter((call) => {
      const init = call[1] as RequestInit | undefined;
      return init?.method === "POST";
    });
    expect(posts).toHaveLength(0);
  });

  // RF24, el hallazgo más caro de esta tarea: el re-post de recuperación
  // tiene que mandar el MISMO tier que se había pedido. Si esto defaulteara a
  // "largo" (o a cualquier valor fijo), recargar la pestaña a mitad de una
  // lectura breve gratis dispararía y cobraría el informe completo de US$ 29.
  it("al recargar a mitad de una breve reintenta la breve, no el informe pago", async () => {
    sessionStorage.setItem(`interpret:${CHART}:es`, "corto");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // el reintento del POST
      .mockResolvedValue(estado(false, 0, 1)); // la breve es una sola sección
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await correr(POLL_MS);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.tier).toBe("corto");
  });

  it("el reintento de un tier no apaga la red de seguridad del otro en la misma pestaña", async () => {
    // El flag de "ya reintenté" está separado por tier a propósito: si no lo
    // estuviera, reintentar la breve marcaría también al completo, y si el
    // proceso del completo muriera después no habría reintento para él.
    // Se simula con dos montajes reales (no escribiendo la clave a mano) para
    // no acoplar el test al formato exacto de la clave.
    sessionStorage.setItem(`interpret:${CHART}:es`, "corto");
    const primeraTanda = vi
      .fn()
      .mockResolvedValueOnce(reply(202)) // reintento de la breve
      .mockResolvedValue(estado(false, 0, 1));
    vi.stubGlobal("fetch", primeraTanda);
    const { unmount } = renderActions(); // interpretations={}: la breve no está completa
    await correr();
    unmount();

    // La breve ya quedó lista; ahora se pidió el completo y la pestaña se
    // recarga a mitad de esa segunda generación.
    sessionStorage.setItem(`interpret:${CHART}:es`, "largo");
    const segundaTanda = vi.fn().mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", segundaTanda);
    renderActions({ interpretations: { es: ["corto"] } });
    await correr();

    const posts = segundaTanda.mock.calls.filter((call) => {
      const init = call[1] as RequestInit | undefined;
      return init?.method === "POST";
    });
    expect(posts).toHaveLength(1);
  });

  it("no recupera un tier que la carta ya tiene completo", () => {
    // Si `interpretations` ya trae "corto" para este idioma, no hay nada que
    // recuperar aunque sessionStorage todavía diga "corto": la generación ya
    // terminó (probablemente la vio otra pestaña) y sondearla de nuevo sería
    // trabajo de más, no un bug de plata, pero sigue siendo ruido a evitar.
    sessionStorage.setItem(`interpret:${CHART}:es`, "corto");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ interpretations: { es: ["corto"] } });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("volver a la carta después de cerrar la pestaña", () => {
  // `sessionStorage` sobrevive un F5 pero muere al cerrar la pestaña, así que
  // no alcanza para "cierro y vuelvo mañana". El servidor ahora dice qué se
  // está escribiendo (`en_curso` en el payload de la carta), y ese dato manda:
  // sin él, la persona vuelve y la carta le ofrece generar otra vez lo que ya
  // pagó y se está escribiendo.
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("muestra la espera cuando el servidor dice que hay algo en curso", async () => {
    const fetchMock = vi.fn().mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ enCurso: { es: ["largo"] } });
    await correr();

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: dict.chart.interpretCompletoConDerecho })).toBeNull();
  });

  it("sondea sin volver a pedir la generación: el servidor ya dijo que está viva", async () => {
    // El POST de reintento existe para el caso en que el proceso murió. Si el
    // servidor declara `en_curso`, su lock está vivo y hay alguien escribiendo:
    // volver a postear sería ruido.
    const fetchMock = vi.fn().mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ enCurso: { es: ["largo"] } });
    await correr();

    const posts = fetchMock.mock.calls.filter((call) => {
      const init = call[1] as RequestInit | undefined;
      return init?.method === "POST";
    });
    expect(posts).toHaveLength(0);
  });

  it("ignora lo que está en curso en otro idioma", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ enCurso: { en: ["largo"] } });
    await correr();

    expect(screen.queryByText(dict.chart.waitTitle)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("la frase de la espera acompaña todo el rato, no sólo los primeros segundos", async () => {
    // El párrafo de arriba pasa a "Vamos por la sección 3 de 8" en cuanto llega
    // el primer sondeo; la frase de color es un renglón aparte y se queda.
    const fetchMock = vi.fn().mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ enCurso: { es: ["largo"] } });
    await correr(POLL_MS);

    expect(screen.getByText(dict.chart.waitColor)).toBeInTheDocument();
    expect(screen.getByText(/secci[óo]n 4 de 8/i)).toBeInTheDocument();
  });

  it("enlaza a los términos, donde se cuenta cómo se escribe la lectura", () => {
    // El pie de la lectura ya no anuncia que la escribe una IA: eso quedó en
    // los Términos de uso, que lo dicen con todas las letras ("genera lecturas
    // interpretativas mediante inteligencia artificial (…) puede contener
    // imprecisiones propias del contenido generado automáticamente"). El único
    // momento donde callarlo sale caro es antes de que alguien ponga US$ 29,
    // así que el bloque de compra deja el camino a un clic.
    renderActions({ freeCredits: 0, paidCredits: 1 });

    const enlace = screen.getByRole("link", { name: dict.chart.comoSeEscribe });
    expect(enlace).toHaveAttribute("href", "/es/legal/terms");
  });

  it("sin derecho, el botón del informe abre el pago en vez de generar", async () => {
    // El backend responde 402 sin derecho, así que pedir la generación sería
    // pedirle a alguien que choque contra una puerta cerrada. El botón lleva a
    // pagar, con la carta atada para que el informe arranque solo al acreditar.
    const assign = vi.fn();
    vi.stubGlobal("location", { assign, href: "" });
    const fetchMock = vi.fn().mockResolvedValue(
      reply(200, { url: "https://checkout.stripe.com/c/pay/cs_test_xyz" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ paidCredits: 0 });
    await clickBoton(dict.chart.interpretCompleto);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/checkout");
    expect(JSON.parse(init.body)).toEqual({
      producto: "informe_natal",
      chart_id: CHART,
      // Vuelve a la página en el idioma en que estaba navegando.
      locale: "es",
    });
    expect(assign).toHaveBeenCalledWith("https://checkout.stripe.com/c/pay/cs_test_xyz");
  });

  it("con derecho, el mismo botón lee en vez de cobrar de nuevo", async () => {
    // Quien compró un pack tiene cinco informes pagos: mandarlo a pagar otra
    // vez sería cobrarle dos veces lo mismo.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(true, 8, 8));
    vi.stubGlobal("fetch", fetchMock);

    renderActions({ paidCredits: 2 });
    await clickBoton(dict.chart.interpretCompletoConDerecho);

    expect(fetchMock.mock.calls[0][0]).toContain("/interpretation");
  });

  it("si el pago no se puede abrir, lo dice y no navega a ningún lado", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { assign, href: "" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(502, { error: "x" })));

    renderActions({ paidCredits: 0 });
    await clickBoton(dict.chart.interpretCompleto);

    expect(screen.getByText(dict.chart.compraFallo)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
