import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewChartForm } from "@/components/NewChartForm";
import { getDict } from "@/lib/i18n";

// El formulario es la puerta de entrada a todo lo demás: si deja pasar datos
// que el backend rechaza, se gasta un viaje y la persona ve un error genérico;
// si manda mal el lugar o la hora, la carta sale calculada para otro cielo.

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));

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

const geocode = (results: unknown[]) => ({ ok: true, json: async () => ({ results }) });
const created = (id: string) => ({ ok: true, status: 201, json: async () => ({ id }) });

function llenarFecha(valor: string) {
  fireEvent.change(screen.getByLabelText(t.date), { target: { value: valor } });
}

/** Escribe el lugar, deja pasar el rebote de la búsqueda y elige el primero. */
async function elegirLugar(fetchMock: ReturnType<typeof vi.fn>) {
  fetchMock.mockResolvedValueOnce(geocode([ROSARIO]));
  fireEvent.change(screen.getByLabelText(t.place), { target: { value: "rosario" } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  fireEvent.click(screen.getByRole("button", { name: /Rosario, Santa Fe, AR/ }));
}

async function enviar() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: t.submit }));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  replace.mockClear();
  refresh.mockClear();
  render(<NewChartForm locale="es" dict={dict} signedIn />);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("NewChartForm", () => {
  it("pide la fecha antes de llamar al backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await enviar();

    expect(screen.getByRole("alert")).toHaveTextContent(t.needDate);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza una fecha futura sin gastar un viaje", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("2999-01-01");
    await enviar();

    expect(screen.getByRole("alert")).toHaveTextContent(t.badDate);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza un año anterior a 1800", async () => {
    // El motor no tiene efemérides para todo: el año 0001 devolvía un 500.
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("0001-07-14");
    await enviar();

    expect(screen.getByRole("alert")).toHaveTextContent(t.badDate);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("pide el lugar aunque la fecha esté bien", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("1989-07-14");
    await enviar();

    expect(screen.getByRole("alert")).toHaveTextContent(t.needPlace);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("manda las coordenadas del lugar elegido y lleva a la carta", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("1989-07-14");
    fireEvent.change(screen.getByLabelText(t.time), { target: { value: "23:45" } });
    await elegirLugar(fetchMock);

    fetchMock.mockResolvedValueOnce(created("abc-123"));
    await enviar();

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/charts");
    expect(JSON.parse(init.body)).toMatchObject({
      date: "1989-07-14",
      time: "23:45",
      time_known: true,
      lat: ROSARIO.lat,
      lng: ROSARIO.lng,
      place_label: ROSARIO.place_query,
    });
    expect(replace).toHaveBeenCalledWith("/es/carta/abc-123");
  });

  it("avisa al backend cuando no se sabe la hora", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("1989-07-14");
    fireEvent.change(screen.getByLabelText(t.time), { target: { value: "23:45" } });
    fireEvent.click(screen.getByLabelText(t.timeUnknown));
    await elegirLugar(fetchMock);

    fetchMock.mockResolvedValueOnce(created("abc"));
    await enviar();

    // La hora tecleada antes no viaja: sin ella no hay casas ni Ascendente.
    const body = JSON.parse(fetchMock.mock.calls.at(-1)![1].body);
    expect(body.time).toBeNull();
    expect(body.time_known).toBe(false);
  });

  it("distingue quedarse sin lecturas breves gratis de un fallo", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    llenarFecha("1989-07-14");
    await elegirLugar(fetchMock);

    fetchMock.mockResolvedValueOnce({ ok: false, status: 402 });
    await enviar();
    expect(screen.getByRole("alert")).toHaveTextContent(t.sinLeerBreve);

    fetchMock.mockResolvedValueOnce({ ok: false, status: 502 });
    await enviar();
    expect(screen.getByRole("alert")).toHaveTextContent(t.failed);
    expect(replace).not.toHaveBeenCalled();
  });

  it("no busca lugares mientras la consulta es corta", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fireEvent.change(screen.getByLabelText(t.place), { target: { value: "ro" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("espera a que se deje de teclear antes de buscar", async () => {
    const fetchMock = vi.fn().mockResolvedValue(geocode([ROSARIO]));
    vi.stubGlobal("fetch", fetchMock);

    const campo = screen.getByLabelText(t.place);
    fireEvent.change(campo, { target: { value: "ros" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    fireEvent.change(campo, { target: { value: "rosar" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).q).toBe("rosar");
  });

  it("avisa cuando el lugar no existe", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(geocode([])));

    fireEvent.change(screen.getByLabelText(t.place), { target: { value: "asdfgh" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(screen.getByText(t.noPlaces)).toBeInTheDocument();
  });

  it("deja cambiar el lugar ya elegido", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await elegirLugar(fetchMock);
    expect(screen.getByText(ROSARIO.place_query)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: t.changePlace }));

    expect(screen.getByLabelText(t.place)).toHaveValue("");
  });
});
