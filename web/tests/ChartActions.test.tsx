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

function renderActions({
  langs = [],
  timeKnown = true,
}: { langs?: string[]; timeKnown?: boolean } = {}) {
  return render(
    <ChartActions locale="es" chartId={CHART} timeKnown={timeKnown} langs={langs} dict={dict} />,
  );
}

/** Respuesta mínima de fetch al POST: sólo se usan `ok` y `status`. */
const reply = (status: number) => ({ ok: status >= 200 && status < 300, status });

/** Respuesta del sondeo de `interpretation/estado`. */
const estado = (completa: boolean, hechas: number, total: number) => ({
  ok: true,
  status: 200,
  json: async () => ({ completa, hechas, total }),
});

/**
 * El efecto de montaje (retomar un informe en curso al recargar la pestaña)
 * consulta `estado` apenas se renderiza, antes de cualquier click: los tests
 * de la interacción con el botón encolan esta respuesta primero para que esa
 * consulta no se coma el valor que el test arma para el POST o el sondeo.
 */
const sinGeneracionEnCurso = estado(false, 0, 8);

beforeEach(() => {
  vi.useFakeTimers();
  refresh.mockClear();
  // El reintento de POST al recargar (HALLAZGO 3) se recuerda en
  // sessionStorage por pestaña: sin limpiarlo, un test contamina al
  // siguiente porque todos usan el mismo CHART.
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

async function clickAndSettle() {
  fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
  await correr();
}

describe("ChartActions", () => {
  it("muestra la lectura cuando el informe termina", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso) // el efecto de montaje
      .mockResolvedValueOnce(reply(202)) // el POST arranca la generación en un hilo
      .mockResolvedValue(estado(true, 8, 8)); // el sondeo la encuentra completa
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
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
      .mockResolvedValueOnce(sinGeneracionEnCurso)
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(true, 8, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS);

    expect(screen.queryByText(dict.chart.waitTitle)).not.toBeInTheDocument();
    expect(document.querySelector(".waiting")).toBeNull();
  });

  it("mientras genera, muestra la espera", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso)
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr();

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
  });

  it("muestra en qué sección va, no una animación ciega", async () => {
    // HALLAZGO 4: `hechas` son las secciones YA terminadas, no la que está en
    // curso. Con 3 hechas, la sección en curso es la 4 (min(hechas+1, total)).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso)
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS);

    expect(screen.getByText(/4 de 8/)).toBeInTheDocument();
  });

  it("HALLAZGO 4: arranca en la sección 1, no en la 0", async () => {
    // El primer sondeo llega a los 5 segundos, antes de que termine la
    // sección 1 (`hechas` todavía en 0): mostrar "sección 0 de 8" es mentira,
    // ya está escribiendo la primera.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso)
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS);

    expect(screen.getByText(/1 de 8/)).toBeInTheDocument();
    expect(screen.queryByText(/0 de 8/)).not.toBeInTheDocument();
  });

  it("no se rinde a los dos minutos", () => {
    // El informe tarda ~6 minutos: 24 intentos × 5 s (2 minutos) se quedaban cortos.
    expect(POLL_TRIES * POLL_MS).toBeGreaterThanOrEqual(10 * 60 * 1000);
  });

  it("avisa que faltan créditos ante un 402", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(402)));
    renderActions();

    await clickAndSettle();

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.noCredits);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("avisa del fallo ante un error del servidor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(503)));
    renderActions();

    await clickAndSettle();

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
  });

  // HALLAZGO 2: el backend devuelve 409 cuando ya hay una generación en curso
  // para esta carta en OTRO idioma (`_sibling_en_curso` en
  // backend/api/interpretation_service.py). No es un fallo duro: es "esperá
  // unos segundos y reintentá". Mostrarlo como `dict.chart.failed` mentía.
  it("avisa que hay una generación en curso ante un 409, y deja reintentar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(409)));
    renderActions();

    await clickAndSettle();

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.generationInProgress);
    // No es un callejón sin salida: el botón sigue ahí para reintentar.
    expect(screen.getByRole("button", { name: dict.chart.interpret })).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("se rinde si el informe no aparece completo dentro del tope, y deja reintentar", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso)
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS * POLL_TRIES);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
    expect(refresh).not.toHaveBeenCalled();
    // El botón vuelve: no es un callejón sin salida.
    expect(screen.getByRole("button", { name: dict.chart.interpret })).toBeInTheDocument();
  }, 20000);

  it("no ofrece el botón si la carta ya tiene lectura en este idioma", () => {
    const { container } = renderActions({ langs: ["es"] });
    expect(container).toBeEmptyDOMElement();
  });

  it("aclara que traducir no cuesta cuando ya existe en otro idioma", () => {
    renderActions({ langs: ["en"] });
    expect(screen.getByText(dict.chart.interpretFreeLang)).toBeInTheDocument();
  });

  it("avisa que faltará una sección si la carta no tiene hora, antes de cobrar", () => {
    renderActions({ timeKnown: false });
    expect(screen.getByText(/sin hora de nacimiento/i)).toBeInTheDocument();
  });

  it("no avisa de la hora cuando la carta ya la tiene", () => {
    renderActions({ timeKnown: true });
    expect(screen.queryByText(/sin hora de nacimiento/i)).not.toBeInTheDocument();
  });

  // `fetch` rechaza ante un corte de red; no resuelve con `ok: false`. En una
  // espera de hasta once minutos eso es cotidiano (wifi que parpadea, la
  // laptop que suspende y despierta), y sin manejarlo la excepción abortaba
  // el bucle entero: el sistema solar quedaba girando para siempre, sin
  // error y sin botón.
  it("un corte de red durante el sondeo no aborta la espera: sigue intentando", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sinGeneracionEnCurso) // el efecto de montaje
      .mockResolvedValueOnce(reply(202)) // el POST arranca la generación
      .mockRejectedValueOnce(new TypeError("Failed to fetch")) // el wifi parpadea
      .mockResolvedValue(estado(true, 8, 8)); // vuelve la red y el informe ya está
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS * 2);

    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("avisa del fallo si el POST no llega por un corte de red, y deja reintentar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderActions();

    await clickAndSettle();

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: dict.chart.interpret })).toBeInTheDocument();
  });

  // Recargar la pestaña a mitad de un informe no debe mostrar el botón como
  // si nada estuviera pasando: el componente vuelve a montar sin memoria de
  // que ya lo pidió, y sólo el backend sabe que sigue escribiendo.
  it("si la pestaña se recarga con un informe en curso, retoma el sondeo en vez del botón", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(estado(false, 3, 8)));
    renderActions();

    await correr(); // el efecto de montaje consulta el estado

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
    expect(screen.getByText(/4 de 8/)).toBeInTheDocument();
  });

  // HALLAZGO 3: si el proceso que generaba murió (deploy, worker reciclado,
  // fallo) no hay nada corriendo del lado del servidor tras la recarga —
  // sondear sin volver a pedirlo deja el progreso congelado hasta el tope.
  // `iniciar_generacion` no cobra dos veces cuando la fila ya existe
  // (backend/api/interpretation_service.py), así que reintentar el POST es
  // seguro.
  it("al recargar con un informe en curso, vuelve a pedir la generación por si el proceso murió", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(estado(false, 3, 8)) // el efecto de montaje ve progreso a medias
      .mockResolvedValueOnce(reply(202)) // el reintento del POST
      .mockResolvedValue(estado(false, 3, 8)); // los sondeos siguientes
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await correr();

    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(String(postUrl)).toContain(`/api/charts/${CHART}/interpretation`);
    expect(postInit).toMatchObject({ method: "POST" });
  });

  it("no repite el reintento si ya lo hizo antes en esta misma pestaña", async () => {
    // Sin este freno, recargar muchas veces mientras el informe se escribe
    // dispararía un POST por recarga: inofensivo para el crédito, pero gasta
    // sin necesidad la cuota diaria de la ruta (`INTERPRETATION_RATE`) y abre
    // hilos de más en el backend.
    const primeraTanda = vi
      .fn()
      .mockResolvedValueOnce(estado(false, 3, 8))
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

  it("si al montar no hay ningún informe en curso, muestra el botón normal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(estado(false, 0, 8)));
    renderActions();

    await correr();

    expect(screen.getByRole("button", { name: dict.chart.interpret })).toBeInTheDocument();
  });
});
