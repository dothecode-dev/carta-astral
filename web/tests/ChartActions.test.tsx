import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChartActions, POLL_MS, POLL_TRIES } from "@/components/ChartActions";
import { getDict } from "@/lib/i18n";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

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

beforeEach(() => {
  vi.useFakeTimers();
  refresh.mockClear();
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
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 0, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr();

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
  });

  it("muestra en qué sección va, no una animación ciega", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(202))
      .mockResolvedValue(estado(false, 3, 8));
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr(POLL_MS);

    expect(screen.getByText(/3 de 8/)).toBeInTheDocument();
  });

  it("no se rinde a los dos minutos", () => {
    // El informe tarda ~4 minutos: 24 intentos × 5 s se quedaban cortos.
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

  it("se rinde si el informe no aparece completo dentro del tope, y deja reintentar", async () => {
    const fetchMock = vi
      .fn()
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
});
