import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VinculoForm } from "@/components/VinculoForm";
import { VINCULO } from "@/content/vinculo";
import { getDict } from "@/lib/i18n";
import * as telemetry from "@/lib/telemetry";

// El formulario de las dos personas de un vínculo. Los rótulos de fecha, hora y
// lugar son los de `dict.newChart` (se reusan, no se repiten); lo propio de
// Vínculo —tipo, alias, errores— viene de `content/vinculo.ts`.
//
// El geocoder se mockea como en `NewChartFormPreview.test.tsx`: timers falsos y
// `fetch` encolado, primero la búsqueda del lugar y después el preview.

const dict = getDict("es");
const nc = dict.newChart;
const t = VINCULO.es;

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
const geocode = (results: unknown[]) => ({ ok: true, json: async () => ({ results }) });
const respuesta = (status: number, body: unknown) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function grupo(legend: string) {
  return within(screen.getByRole("group", { name: legend }));
}

async function completarPersona(
  legend: string,
  fecha: string,
  opciones: { alias?: string; hora?: string; sinHora?: boolean } = {},
) {
  const g = grupo(legend);
  if (opciones.alias) fireEvent.change(g.getByLabelText(t.alias), { target: { value: opciones.alias } });
  fireEvent.change(g.getByLabelText(nc.date), { target: { value: fecha } });
  if (opciones.hora) fireEvent.change(g.getByLabelText(nc.time), { target: { value: opciones.hora } });
  if (opciones.sinHora) fireEvent.click(g.getByLabelText(nc.timeUnknown));
  fetchMock.mockResolvedValueOnce(geocode([ROSARIO]));
  fireEvent.change(g.getByLabelText(nc.place), { target: { value: "rosario" } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  fireEvent.click(g.getByRole("button", { name: /Rosario, Santa Fe, AR/ }));
}

async function enviar(resp: unknown) {
  fetchMock.mockResolvedValueOnce(resp);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: t.calcular }));
  });
}

const renderForm = (onResultado = vi.fn()) => {
  render(<VinculoForm locale="es" dict={dict} onResultado={onResultado} />);
  return onResultado;
};

describe("VinculoForm", () => {
  it("no deja calcular sin las dos personas completas", async () => {
    renderForm();
    expect(screen.getByRole("button", { name: t.calcular })).toBeDisabled();
    await completarPersona(t.personaA, "1976-05-31");
    expect(screen.getByRole("button", { name: t.calcular })).toBeDisabled();
    await completarPersona(t.personaB, "1980-11-02");
    expect(screen.getByRole("button", { name: t.calcular })).toBeEnabled();
  });

  it("ofrece los cuatro tipos, con pareja por defecto", () => {
    renderForm();
    const select = screen.getByLabelText(t.tipoLabel) as HTMLSelectElement;
    expect(select.value).toBe("pareja");
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "pareja",
      "trabajo",
      "familia",
      "amistad",
    ]);
  });

  it("manda las dos personas con el idioma, sin nombre ni alias", async () => {
    renderForm();
    await completarPersona(t.personaA, "1976-05-31", { alias: "Ana", hora: "19:30" });
    await completarPersona(t.personaB, "1980-11-02", { alias: "Beto", hora: "08:15" });
    await enviar(respuesta(200, { a: {}, b: {}, aspectos: [] }));

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/vinculo/preview");
    const cuerpo = JSON.parse(init.body);
    expect(cuerpo.lang).toBe("es");
    expect(cuerpo.a).toMatchObject({ date: "1976-05-31", time: "19:30", time_known: true, name: null });
    expect(cuerpo.b).toMatchObject({ date: "1980-11-02", time: "08:15", time_known: true, name: null });
    expect(init.body).not.toContain("Ana");
    expect(init.body).not.toContain("Beto");
  });

  it("devuelve el resultado con el tipo elegido y los alias", async () => {
    const onResultado = renderForm();
    fireEvent.change(screen.getByLabelText(t.tipoLabel), { target: { value: "trabajo" } });
    await completarPersona(t.personaA, "1976-05-31", { alias: " Ana " });
    await completarPersona(t.personaB, "1980-11-02", { alias: "Beto" });
    await enviar(respuesta(200, { a: {}, b: {}, aspectos: [] }));

    expect(onResultado).toHaveBeenCalledWith(
      { a: {}, b: {}, aspectos: [] },
      "trabajo",
      { a: "Ana", b: "Beto" },
    );
  });

  it("la hora desconocida de una persona no afecta a la otra", async () => {
    renderForm();
    await completarPersona(t.personaA, "1976-05-31", { hora: "19:30" });
    await completarPersona(t.personaB, "1980-11-02", { hora: "08:15", sinHora: true });
    await enviar(respuesta(200, { a: {}, b: {}, aspectos: [] }));

    const cuerpo = JSON.parse(fetchMock.mock.calls.at(-1)![1].body);
    expect(cuerpo.a).toMatchObject({ time: "19:30", time_known: true });
    expect(cuerpo.b).toMatchObject({ time: null, time_known: false });
  });

  it("una fecha imposible se rechaza sin llamar al backend", async () => {
    renderForm();
    await completarPersona(t.personaA, "1700-01-01");
    await completarPersona(t.personaB, "1980-11-02");
    const llamadasAntes = fetchMock.mock.calls.length;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.calcular }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(nc.badDate);
    expect(fetchMock.mock.calls.length).toBe(llamadasAntes);
  });

  it("misma persona: avisa y registra el motivo", async () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    renderForm();
    await completarPersona(t.personaA, "1976-05-31");
    await completarPersona(t.personaB, "1976-05-31");
    await enviar(respuesta(400, { error: "misma_persona" }));
    expect(screen.getByRole("alert")).toHaveTextContent(t.errores.misma_persona);
    expect(track).toHaveBeenCalledWith("vinculo_preview_fallido", { motivo: "misma_persona" });
  });

  it("429 muestra el mensaje de probar más tarde", async () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    renderForm();
    await completarPersona(t.personaA, "1976-05-31");
    await completarPersona(t.personaB, "1980-11-02");
    await enviar(respuesta(429, { error: "demasiadas" }));
    expect(screen.getByRole("alert")).toHaveTextContent(t.errores.demasiadas);
    expect(track).toHaveBeenCalledWith("vinculo_preview_fallido", { motivo: "demasiadas" });
  });

  it("un motivo que el servidor inventa se reduce a no_disponible", async () => {
    renderForm();
    await completarPersona(t.personaA, "1976-05-31");
    await completarPersona(t.personaB, "1980-11-02");
    await enviar(respuesta(502, { error: "<b>x</b>" }));
    expect(screen.getByRole("alert")).toHaveTextContent(t.errores.no_disponible);
  });

  it("si la red se cae, cuenta como no_disponible", async () => {
    const track = vi.spyOn(telemetry, "track").mockImplementation(() => {});
    renderForm();
    await completarPersona(t.personaA, "1976-05-31");
    await completarPersona(t.personaB, "1980-11-02");
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.calcular }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(t.errores.no_disponible);
    expect(track).toHaveBeenCalledWith("vinculo_preview_fallido", { motivo: "no_disponible" });
  });

  it("después de un error se puede volver a intentar", async () => {
    const onResultado = renderForm();
    await completarPersona(t.personaA, "1976-05-31");
    await completarPersona(t.personaB, "1980-11-02");
    await enviar(respuesta(429, { error: "demasiadas" }));
    expect(screen.getByRole("button", { name: t.calcular })).toBeEnabled();
    await enviar(respuesta(200, { a: {}, b: {}, aspectos: [] }));
    expect(onResultado).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
