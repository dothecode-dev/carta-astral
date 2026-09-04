import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewChartForm } from "@/components/NewChartForm";
import { getDict } from "@/lib/i18n";

// El camino del visitante que todavía no tiene cuenta: calcula, ve SU carta, y
// recién cuando quiere la lectura aparece el registro. Lo que se prueba acá es
// que ese camino no toque la cuenta —no crea nada— y que lo cargado sobreviva
// al viaje por el login, que es donde se perdía todo antes.

const replace = vi.fn();
const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh, push }) }));

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
    placements: [
      { name: "Sun", sign: "Gem", abs_pos: 70.5, house: "First_House", retrograde: false },
    ],
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

/** Llena el formulario y envía. `respuesta` es lo que contesta el preview:
 *  se encola DESPUÉS de la del geocodificador, que es la que va primera. */
async function completarYEnviar(fetchMock: ReturnType<typeof vi.fn>, respuesta: unknown) {
  fireEvent.change(screen.getByLabelText(t.date), { target: { value: "1976-05-31" } });
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

const CALCULADA = { ok: true, status: 200, json: async () => CARTA };

describe("sin cuenta", () => {
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

  it("calcula contra el preview y no crea ninguna carta", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls).toContain("/api/charts/preview");
    expect(urls).not.toContain("/api/charts");
    expect(screen.getByText(t.previewTitle)).toBeTruthy();
  });

  it("no manda a entrar antes de mostrar la carta", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    expect(push).not.toHaveBeenCalled();
  });

  it("al pedir la lectura guarda lo cargado y manda a entrar volviendo acá", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.previewCta }));
    });

    expect(push).toHaveBeenCalledWith("/es/entrar?next=%2Fes%2Fnueva");
    const guardado = JSON.parse(sessionStorage.getItem("astra-carta-pendiente") ?? "null");
    expect(guardado).toMatchObject({ date: "1976-05-31", lat: ROSARIO.lat, lng: ROSARIO.lng });
  });

  it("si el techo por IP corta, avisa en vez de quedarse mudo", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, { ok: false, status: 429, json: async () => ({}) });

    expect(screen.getByRole("alert").textContent).toBe(t.failed);
  });
});

describe("al volver del login", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    push.mockClear();
    replace.mockClear();
    sessionStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("guarda la carta que ya había visto y la lleva a ella", async () => {
    sessionStorage.setItem(
      "astra-carta-pendiente",
      JSON.stringify({ date: "1976-05-31", lat: -32.9, lng: -60.6, time: null, time_known: false, name: null, place_label: "Rosario" }),
    );
    fetchMock.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: "abc" }) });

    await act(async () => {
      render(<NewChartForm locale="es" dict={dict} signedIn />);
    });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/charts");
    expect(replace).toHaveBeenCalledWith("/es/carta/abc");
    // Se limpia sí o sí: si quedara, volver a esta página crearía la carta de nuevo.
    expect(sessionStorage.getItem("astra-carta-pendiente")).toBeNull();
  });

  it("sin nada pendiente muestra el formulario y no crea nada", async () => {
    await act(async () => {
      render(<NewChartForm locale="es" dict={dict} signedIn />);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText(t.date)).toBeTruthy();
  });
});
