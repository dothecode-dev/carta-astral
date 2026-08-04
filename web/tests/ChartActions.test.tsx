import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChartActions } from "@/components/ChartActions";
import { getDict } from "@/lib/i18n";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const dict = getDict("es");
const CHART = "89151d40-e263-4d34-81e0-2fb434f70243";

function renderActions(langs: string[] = []) {
  return render(
    <ChartActions locale="es" chartId={CHART} langs={langs} dict={dict} />,
  );
}

/** Respuesta mínima de fetch: sólo se usan `ok` y `status`. */
const reply = (status: number) => ({ ok: status >= 200 && status < 300, status });

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
  it("muestra la lectura cuando la generación sale bien", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(200)));
    renderActions();

    await clickAndSettle();

    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("apaga la espera cuando la lectura llega", async () => {
    // La animación del sistema solar y los tres pasos quedaban encendidos para
    // siempre debajo del texto ya escrito: `router.refresh()` no avisa cuándo
    // termina y nadie apagaba el estado de espera.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(200)));
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr();

    expect(screen.queryByText(dict.chart.waitTitle)).not.toBeInTheDocument();
    expect(document.querySelector(".waiting")).toBeNull();
  });

  it("mientras genera, muestra la espera", async () => {
    let resolver: (r: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((r) => (resolver = r))));
    renderActions();

    fireEvent.click(screen.getByRole("button", { name: dict.chart.interpret }));
    await correr();

    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
    await act(async () => resolver(reply(200)));
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

  // El caso que rompió en producción el 02-08: dos pedidos a la vez sobre la
  // misma carta. El segundo recibía 409 y la web decía "no pudimos generar"
  // mientras la lectura se estaba escribiendo.
  it("ante un 409 espera en vez de dar la lectura por perdida", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(409)) // el POST rebota contra el lock
      .mockResolvedValueOnce(reply(404)) // todavía no está escrita
      .mockResolvedValue(reply(200)); // la otra petición terminó
    vi.stubGlobal("fetch", fetchMock);
    renderActions();

    await clickAndSettle();

    // No hay error a la vista: sigue la espera.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(dict.chart.waitTitle)).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();

    await correr(11000); // dos consultas

    expect(refresh).toHaveBeenCalledOnce();
    const consultas = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("lang=es"),
    );
    expect(consultas).toHaveLength(2);
  });

  it("se rinde si la lectura no aparece en dos minutos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(reply(409)).mockResolvedValue(reply(404)),
    );
    renderActions();

    await clickAndSettle();
    await correr(125000);

    expect(screen.getByRole("alert")).toHaveTextContent(dict.chart.failed);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("no ofrece el botón si la carta ya tiene lectura en este idioma", () => {
    const { container } = renderActions(["es"]);
    expect(container).toBeEmptyDOMElement();
  });

  it("aclara que traducir no cuesta cuando ya existe en otro idioma", () => {
    renderActions(["en"]);
    expect(screen.getByText(dict.chart.interpretFreeLang)).toBeInTheDocument();
  });
});
