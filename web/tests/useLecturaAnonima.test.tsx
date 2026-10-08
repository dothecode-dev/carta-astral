import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const track = vi.fn();
vi.mock("@/lib/telemetry", () => ({ track: (...a: unknown[]) => track(...a) }));

import { useLecturaAnonima } from "@/components/useLecturaAnonima";

const CARTA = { firma: {} } as never;
const res = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("useLecturaAnonima", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.useFakeTimers();
    track.mockClear();
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("pide, consulta hasta lista, guarda y avisa", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "lista", texto: "t", lang: "es", disclaimer: "d" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "1976-05-31" }, CARTA, "es"); });
    expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
    const guardada = JSON.parse(localStorage.getItem("astra-lectura-anonima")!);
    expect(guardada.texto).toBe("t");
    expect(guardada.datos).toEqual({ date: "1976-05-31" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_pedida", {});
    expect(track).toHaveBeenCalledWith("lectura_anonima_generada", {});
  });

  it.each([
    [409, "usado", { tipo: "usada" }, "lectura_anonima_usada"],
    [429, "ip", { tipo: "sin_cupo" }, "lectura_anonima_fallida"],
    [503, "cupo", { tipo: "sin_cupo" }, "lectura_anonima_fallida"],
    [503, "mantenimiento", { tipo: "mantenimiento" }, "lectura_anonima_fallida"],
  ])("%s %s → %o", async (status, motivo, esperado, evento) => {
    fetchMock.mockReturnValueOnce(res(status, { motivo }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    expect(result.current.estado).toEqual(esperado);
    expect(track.mock.calls.map((c) => c[0])).toContain(evento);
  });

  it("ocupado reintenta solo a los 5 s, hasta 3 veces", async () => {
    // Una Response nueva por llamada: su cuerpo se lee una sola vez.
    fetchMock.mockImplementation(() => res(503, { motivo: "ocupado" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: true });
    for (let i = 0; i < 3; i++) await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "ocupado" });
  });

  it("a los 60 s sin lista corta como timeout", async () => {
    fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
    fetchMock.mockImplementation(() => res(200, { estado: "generando" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "timeout" });
  });

  it("fallida del backend", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "fallida" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "modelo" });
  });

  it("reiniciar corta la espera: una lectura que llega tarde no aparece ni se guarda", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "de A", lang: "es", disclaimer: "" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(localStorage.getItem("astra-lectura-anonima")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reiniciar con un sondeo en vuelo descarta su respuesta", async () => {
    let soltar!: (r: Response) => void;
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(new Promise<Response>((ok) => { soltar = ok; }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    act(() => { result.current.reiniciar(); });
    await act(async () => {
      soltar(new Response(JSON.stringify({ estado: "lista", texto: "de A", lang: "es", disclaimer: "" }), { status: 200 }));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(localStorage.getItem("astra-lectura-anonima")).toBeNull();
  });

  it("pedir dos veces deja un solo ciclo de sondeo", async () => {
    fetchMock.mockImplementation((url: string, init?: { method?: string }) =>
      init?.method === "POST" ? res(202, { estado: "generando" }) : res(200, { estado: "generando" }),
    );
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const gets = fetchMock.mock.calls.filter((c) => !c[1]?.method).length;
    expect(gets).toBe(1);
  });
});
