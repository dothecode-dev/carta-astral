import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewChartForm } from "@/components/NewChartForm";
import { getDict } from "@/lib/i18n";

// El trato (cómo quiere la persona que le hablemos) se elige al calcular y tiene
// que llegar al backend por los tres caminos: crear con sesión, comprar sin
// cuenta y volver del login con la carta guardada en `sessionStorage`.

const replace = vi.fn();
const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh, push }) }));
vi.mock("@/lib/telemetry", () => ({ track: vi.fn() }));

const dict = getDict("es");
const t = dict.newChart;

const ROSARIO = {
  place_query: "Rosario, Santa Fe, AR",
  name: "Rosario",
  lat: -32.94682,
  lng: -60.63932,
  tz_name: "America/Argentina/Cordoba",
  country_code: "AR",
  admin1: "Santa Fe",
  population: 1193605,
};

const CARTA = {
  data: {
    placements: [{ name: "Sun", sign: "Gem", abs_pos: 70.5, house: "First_House", retrograde: false }],
    houses: null,
    angles: null,
    aspects: [],
    flags: {
      moon_approximate: false,
      precision_degraded: false,
      bodies_missing: false,
      house_system_fallback: false,
    },
  },
};

const geocode = (results: unknown[]) => ({ ok: true, json: async () => ({ results }) });
const CALCULADA = { ok: true, status: 200, json: async () => CARTA };

async function completarYEnviar(
  fetchMock: ReturnType<typeof vi.fn>,
  respuesta: unknown,
  trato?: string,
) {
  fireEvent.change(screen.getByLabelText(t.date), { target: { value: "1976-05-31" } });
  if (trato !== undefined) {
    fireEvent.change(screen.getByLabelText(t.tratoLabel), { target: { value: trato } });
  }
  fetchMock.mockResolvedValueOnce(geocode([ROSARIO]));
  fireEvent.change(screen.getByLabelText(t.place), { target: { value: "rosario" } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  fireEvent.click(screen.getByRole("button", { name: /Rosario, Santa Fe, AR/ }));
  fetchMock.mockResolvedValueOnce(respuesta);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: t.submit }));
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  push.mockClear();
  replace.mockClear();
  sessionStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("el selector del trato", () => {
  it("está debajo del nombre, con las tres opciones y «sin elegir» inicial", () => {
    render(<NewChartForm locale="es" dict={dict} />);
    const select = screen.getByLabelText(t.tratoLabel) as HTMLSelectElement;

    expect(select.value).toBe("");
    const opciones = Array.from(select.options).map((o) => [o.value, o.textContent]);
    expect(opciones).toEqual([
      ["", t.tratoVacio],
      ["femenino", t.tratoFemenino],
      ["masculino", t.tratoMasculino],
      ["neutro", t.tratoNeutro],
    ]);
    expect(screen.getByText(t.tratoNota)).toBeTruthy();

    const nombre = screen.getByLabelText(t.name);
    expect(nombre.compareDocumentPosition(select) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it.each(["es", "en", "pt"] as const)("tiene textos en %s", (locale) => {
    const d = getDict(locale).newChart;
    for (const k of [
      "tratoLabel",
      "tratoFemenino",
      "tratoMasculino",
      "tratoNeutro",
      "tratoVacio",
      "tratoNota",
    ] as const) {
      expect(d[k].length).toBeGreaterThan(0);
    }
  });
});

describe("el trato llega al backend", () => {
  it("con sesión, crear la carta manda el trato en POST /api/charts", async () => {
    render(<NewChartForm locale="es" dict={dict} signedIn />);
    await completarYEnviar(fetchMock, { ok: true, status: 201, json: async () => ({ id: "abc" }) }, "femenino");

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/charts");
    expect(JSON.parse(init.body)).toMatchObject({ trato: "femenino" });
  });

  it("sin sesión, «Leer el informe completo» manda el trato al checkout anónimo", async () => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA, "masculino");
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ url: "https://stripe.test/c" }) });
    vi.stubGlobal("location", { ...window.location, assign: vi.fn() });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Leer el informe completo · US\$ 29/ }));
    });

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/checkout/anonimo");
    expect(JSON.parse(init.body)).toMatchObject({ trato: "masculino", locale: "es" });
  });

  it("sin sesión, «Leer qué dice» manda el trato a la lectura sin cuenta", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA, "neutro");
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ estado: "generando" }), { status: 202 }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.previewCta }));
    });

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/lectura-anonima");
    expect(JSON.parse(init.body)).toMatchObject({ trato: "neutro", date: "1976-05-31" });
  });

  it("al volver logueado del login, retoma lo guardado y el POST lleva el trato", async () => {
    // Ya nadie escribe esta clave desde la vista previa (la lectura se hace
    // sin cuenta), pero quien entra por /entrar por su cuenta puede traerla.
    sessionStorage.setItem(
      "astra-carta-pendiente",
      JSON.stringify({ trato: "neutro", date: "1976-05-31" }),
    );
    fetchMock.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: "abc" }) });
    await act(async () => {
      render(<NewChartForm locale="es" dict={dict} signedIn />);
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/charts");
    expect(JSON.parse(init.body)).toMatchObject({ trato: "neutro", date: "1976-05-31" });
  });

  it("sin elegir, el trato va vacío", async () => {
    render(<NewChartForm locale="es" dict={dict} signedIn />);
    await completarYEnviar(fetchMock, { ok: true, status: 201, json: async () => ({ id: "abc" }) });

    const [, init] = fetchMock.mock.calls.at(-1)!;
    expect(JSON.parse(init.body).trato ?? "").toBe("");
  });
});
