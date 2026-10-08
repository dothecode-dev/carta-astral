import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const track = vi.fn();
vi.mock("@/lib/telemetry", () => ({ track: (...a: unknown[]) => track(...a) }));

import { useLecturaAnonima } from "@/components/useLecturaAnonima";

const CARTA = { firma: {} } as never;
const CARTA_B = { firma: { b: 1 } } as never;
const res = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

// Los ids de pedido son predecibles en los tests: P1 para el primer `pedir`,
// P2 para el segundo…
const P1 = "00000000-0000-4000-8000-000000000001";
const P2 = "00000000-0000-4000-8000-000000000002";
const guardada = () => JSON.parse(localStorage.getItem("astra-lectura-anonima") ?? "null");
const posts = (f: ReturnType<typeof vi.fn>) =>
  f.mock.calls.filter((c) => c[1]?.method === "POST").map((c) => JSON.parse(c[1].body));

describe("useLecturaAnonima", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.useFakeTimers();
    track.mockClear();
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    let n = 0;
    vi.spyOn(globalThis.crypto, "randomUUID").mockImplementation(
      () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}` as `${string}-${string}-${string}-${string}-${string}`,
    );
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("pide, consulta hasta lista, guarda y avisa", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "generando", pedido: P1 }))
      .mockReturnValueOnce(res(200, { estado: "lista", texto: "t", lang: "es", disclaimer: "d", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "1976-05-31" }, CARTA, "es"); });
    expect(posts(fetchMock)[0]).toMatchObject({ date: "1976-05-31", lang: "es", pedido: P1 });
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
    // Los reintentos por «ocupado» son el MISMO pedido, no uno nuevo.
    expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1, P1, P1, P1]);
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "ocupado" });
  });

  it("a los 60 s sin lista corta como timeout", async () => {
    fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
    fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "timeout" });
  });

  it("fallida del backend", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "fallida", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "modelo" });
  });

  // Volver mientras se escribe NO tira la lectura gratis (final review I1):
  // la espera sigue de fondo, no pinta nada y guarda la lectura con SU carta.
  it("reiniciar con un timer pendiente: no pinta, pero la guarda con la carta original", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "de A", lang: "es", disclaimer: "", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(guardada()).toMatchObject({ texto: "de A", datos: { date: "A" }, carta: { firma: {} } });
    // Un solo sondeo: se detiene al recibirla.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.guardadas).toBe(1);
  });

  it("reiniciar con un sondeo en vuelo: no pinta su respuesta, pero la guarda con la carta original", async () => {
    let soltar!: (r: Response) => void;
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(new Promise<Response>((ok) => { soltar = ok; }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    act(() => { result.current.reiniciar(); });
    await act(async () => {
      soltar(new Response(JSON.stringify({ estado: "lista", texto: "de A", lang: "es", disclaimer: "", pedido: P1 }), { status: 200 }));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(guardada()).toMatchObject({ texto: "de A", datos: { date: "A" } });
  });

  it("reiniciar con el POST en vuelo: al llegar el 202 sondea de fondo y la guarda con su carta", async () => {
    let soltar!: (r: Response) => void;
    fetchMock
      .mockReturnValueOnce(new Promise<Response>((ok) => { soltar = ok; }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "de A", lang: "es", disclaimer: "", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    let enVuelo!: Promise<void>;
    act(() => { enVuelo = result.current.pedir({ date: "A" }, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => {
      soltar(new Response(JSON.stringify({ estado: "generando" }), { status: 202 }));
      await enVuelo;
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(guardada()).toMatchObject({ texto: "de A", datos: { date: "A" } });
  });

  it("de fondo, una fallida termina sin pintar ni guardar", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "fallida", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(guardada()).toBeNull();
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "modelo" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("de fondo, el corte de 60 s termina sin pintar", async () => {
    fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
    fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(result.current.estado).toEqual({ tipo: "nada" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "timeout" });
    const llamadas = fetchMock.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(fetchMock.mock.calls.length).toBe(llamadas);
  });

  it("un pedido nuevo que recibe 409 no corta la espera de fondo del anterior", async () => {
    fetchMock.mockImplementation((url: string, init?: { method?: string; body?: string }) => {
      if (init?.method === "POST") {
        return JSON.parse(init.body!).pedido === P1
          ? res(202, { estado: "generando" })
          : res(409, { motivo: "usado" });
      }
      return res(200, { estado: "generando", pedido: P1 });
    });
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); }); // un sondeo de fondo: generando
    await act(async () => { await result.current.pedir({ date: "B" }, CARTA_B, "es"); });
    expect(result.current.estado).toEqual({ tipo: "usada" });
    expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1, P2]);
    fetchMock.mockImplementation(() =>
      res(200, { estado: "lista", texto: "de A", lang: "es", disclaimer: "", pedido: P1 }),
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    // B sigue viendo «usada»; la de A quedó guardada con la carta y los datos de A.
    expect(result.current.estado).toEqual({ tipo: "usada" });
    expect(guardada()).toMatchObject({ texto: "de A", datos: { date: "A" }, carta: { firma: {} } });
    expect(fetchMock.mock.calls.filter((c) => !c[1]?.method)).toHaveLength(2);
  });

  // C1: una lista de OTRO pedido es la lectura de otra carta.
  it("una lista con otro pedido no se pinta ni se guarda para la carta actual", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "de A", lang: "es", disclaimer: "", pedido: P2 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "B" }, CARTA_B, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.estado).toEqual({ tipo: "usada" });
    expect(guardada()).toBeNull();
    expect(track).not.toHaveBeenCalledWith("lectura_anonima_generada", {});
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("una lista sin pedido tampoco se acepta", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "x", lang: "es", disclaimer: "" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(result.current.estado).not.toMatchObject({ tipo: "lista" });
    expect(guardada()).toBeNull();
  });

  it("pedir dos veces deja un solo ciclo de sondeo", async () => {
    fetchMock.mockImplementation((url: string, init?: { method?: string }) =>
      init?.method === "POST" ? res(202, { estado: "generando" }) : res(200, { estado: "generando", pedido: P1 }),
    );
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const gets = fetchMock.mock.calls.filter((c) => !c[1]?.method).length;
    expect(gets).toBe(1);
    // Ni un segundo POST: con otro id, el backend lo tomaría por otra carta.
    expect(posts(fetchMock)).toHaveLength(1);
    expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: false });
  });
});
