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
const pendiente = () => JSON.parse(localStorage.getItem("astra-lectura-pedido") ?? "null");
const gets = (f: ReturnType<typeof vi.fn>) => f.mock.calls.filter((c) => !c[1]?.method).length;
const acuses = (f: ReturnType<typeof vi.fn>) =>
  f.mock.calls.filter((c) => c[1]?.method === "DELETE").map((c) => c[0]);
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

  // v3: el fin normal lo decide el backend (latido); el corte de la web es
  // una red de seguridad de 5 min, no de 60 s.
  it("a los 5 min sin lista corta como timeout, no antes", async () => {
    fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
    fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); });
    expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(240_000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    expect(track).toHaveBeenCalledWith("lectura_anonima_fallida", { motivo: "timeout" });
  });

  it("«Probar de nuevo» tras una fallida, con la misma carta, reusa el pedido", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "fallida", pedido: P1 }))
      .mockReturnValueOnce(res(202, { estado: "generando" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1, P1]);
    expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: false });
  });

  it("«Probar de nuevo» tras el corte, con la misma carta, reusa el pedido", async () => {
    fetchMock.mockImplementation((url: string, init?: { method?: string }) =>
      init?.method === "POST" ? res(202, { estado: "generando" }) : res(200, { estado: "generando", pedido: P1 }),
    );
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(301_000); });
    expect(result.current.estado).toEqual({ tipo: "fallida" });
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1, P1]);
  });

  it("tras una fallida, OTRA carta lleva un pedido nuevo", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "generando" }))
      .mockReturnValueOnce(res(200, { estado: "fallida", pedido: P1 }))
      .mockReturnValueOnce(res(202, { estado: "generando" }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    await act(async () => { await result.current.pedir({ date: "B" }, CARTA_B, "es"); });
    expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1, P2]);
  });

  it("un 202 con estado lista (escrita y sin acusar) va derecho al GET", async () => {
    fetchMock
      .mockReturnValueOnce(res(202, { estado: "lista" }))
      .mockImplementation(() => res(200, { estado: "lista", texto: "t", lang: "es", disclaimer: "d", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
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
    // Un solo sondeo: se detiene al recibirla. (El POST, el GET y el acuse.)
    expect(gets(fetchMock)).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
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

  it("de fondo, el corte de 5 min termina sin pintar", async () => {
    fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
    fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
    const { result } = renderHook(() => useLecturaAnonima());
    await act(async () => { await result.current.pedir({}, CARTA, "es"); });
    act(() => { result.current.reiniciar(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(301_000); });
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

  // §11 v3: entrega en dos tiempos y pedido en curso persistido.
  describe("acuse y pedido en curso", () => {
    const LISTA_P1 = { estado: "lista", texto: "t", lang: "es", disclaimer: "d", pedido: P1 };
    const PEND = { pedido: P1, carta: { firma: {} }, datos: { date: "A" } };

    it("al pedir guarda el pedido en curso con su carta y sus datos", async () => {
      fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      expect(pendiente()).toMatchObject(PEND);
      expect(typeof pendiente().vence).toBe("number");
    });

    it("con la lista: la guarda, después acusa con su pedido y borra el pedido en curso", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(200, LISTA_P1))
        .mockReturnValueOnce(Promise.resolve(new Response(null, { status: 204 })));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(guardada()).toMatchObject({ texto: "t" });
      expect(acuses(fetchMock)).toEqual([`/api/lectura-anonima?pedido=${P1}`]);
      // El acuse va DESPUÉS del GET que la trajo (y del guardado).
      expect(fetchMock.mock.calls.at(-1)![1]).toMatchObject({ method: "DELETE" });
      expect(pendiente()).toBeNull();
    });

    it("si el acuse falla, la lectura queda igual y el pedido en curso se borra", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(200, LISTA_P1))
        .mockImplementationOnce(() => Promise.reject(new TypeError("red")));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
      expect(guardada()).toMatchObject({ texto: "t" });
      expect(pendiente()).toBeNull();
    });

    it.each([
      ["una fallida", [res(202, { estado: "generando" }), res(200, { estado: "fallida", pedido: P1 })], 1000],
      ["un 409", [res(409, { motivo: "usado" })], 0],
      ["una lista de otro pedido", [res(202, { estado: "generando" }), res(200, { ...LISTA_P1, pedido: P2 })], 1000],
    ])("%s borra el pedido en curso", async (_n, respuestas, avance) => {
      for (const r of respuestas) fetchMock.mockReturnValueOnce(r);
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(avance); });
      expect(pendiente()).toBeNull();
      expect(acuses(fetchMock)).toEqual([]);
    });

    it("el corte borra el pedido en curso", async () => {
      fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
      fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({}, CARTA, "es"); });
      expect(pendiente()).not.toBeNull();
      await act(async () => { await vi.advanceTimersByTimeAsync(301_000); });
      expect(pendiente()).toBeNull();
    });

    it("al montar con un pedido en curso, retoma de fondo: guarda con SU carta, acusa y no pinta", async () => {
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, vence: Date.now() + 60_000 }));
      fetchMock
        .mockReturnValueOnce(res(200, { estado: "generando", pedido: P1 }))
        .mockReturnValueOnce(res(200, LISTA_P1))
        .mockReturnValueOnce(Promise.resolve(new Response(null, { status: 204 })));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(gets(fetchMock)).toBe(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(result.current.estado).toEqual({ tipo: "nada" });
      expect(guardada()).toMatchObject({ texto: "t", datos: { date: "A" }, carta: { firma: {} } });
      expect(result.current.guardadas).toBe(1);
      expect(acuses(fetchMock)).toEqual([`/api/lectura-anonima?pedido=${P1}`]);
      expect(pendiente()).toBeNull();
      expect(posts(fetchMock)).toEqual([]);
    });

    it("al montar con un pedido en curso que terminó fallida, lo borra sin pintar ni guardar", async () => {
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, vence: Date.now() + 60_000 }));
      fetchMock.mockReturnValueOnce(res(200, { estado: "fallida", pedido: P1 }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(result.current.estado).toEqual({ tipo: "nada" });
      expect(guardada()).toBeNull();
      expect(pendiente()).toBeNull();
    });

    it("al montar con un pedido en curso, el corte es su vencimiento si llega antes", async () => {
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, vence: Date.now() + 10_000 }));
      fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
      renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(11_000); });
      expect(pendiente()).toBeNull();
      const n = gets(fetchMock);
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(gets(fetchMock)).toBe(n);
    });

    it("al montar con un pedido vencido no consulta nada", async () => {
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, vence: Date.now() - 1 }));
      renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("desmontar corta la espera retomada", async () => {
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, vence: Date.now() + 60_000 }));
      fetchMock.mockImplementation(() => res(200, { estado: "generando", pedido: P1 }));
      const { unmount } = renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      unmount();
      const n = fetchMock.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(fetchMock.mock.calls.length).toBe(n);
    });

    it("otra pestaña ya la guardó y acusó: el 404 muestra la guardada, no «fallida»", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockImplementationOnce(() => {
          // Mientras esta pestaña espera, la otra guarda la lectura y la acusa.
          localStorage.setItem("astra-lectura-anonima", JSON.stringify({
            carta: { firma: {} }, datos: { date: "A" }, texto: "t", lang: "es", disclaimer: "d",
            pedido: P1, vence: Date.now() + 60_000,
          }));
          return res(404, {});
        });
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
      expect(track.mock.calls.map((c) => c[0])).not.toContain("lectura_anonima_fallida");
      // La contó la otra pestaña: acá no se cuenta dos veces.
      expect(track.mock.calls.map((c) => c[0])).not.toContain("lectura_anonima_generada");
    });

    it("un 404 sin lectura guardada de ese pedido sigue siendo «fallida»", async () => {
      localStorage.setItem("astra-lectura-anonima", JSON.stringify({
        carta: { firma: {} }, datos: { date: "Z" }, texto: "vieja", lang: "es", disclaimer: "d",
        pedido: P2, vence: Date.now() + 60_000,
      }));
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(404, {}));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(result.current.estado).toEqual({ tipo: "fallida" });
    });

    it("la lectura guardada lleva el id de su pedido", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(200, LISTA_P1));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(guardada()).toMatchObject({ pedido: P1 });
    });

    it("tras recargar, pedir la MISMA carta adopta la espera retomada en vez de dar «usada»", async () => {
      const P9 = "00000000-0000-4000-8000-000000000009";
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, pedido: P9, lang: "es", vence: Date.now() + 60_000 }));
      fetchMock
        .mockReturnValueOnce(res(200, { estado: "generando", pedido: P9 }))
        .mockReturnValueOnce(res(200, { estado: "generando", pedido: P9 }))
        .mockReturnValueOnce(res(200, { ...LISTA_P1, pedido: P9 }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      // Otra instancia de la carta (recalculada), con los mismos datos.
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA_B, "es"); });
      expect(posts(fetchMock)).toEqual([]);
      expect(result.current.estado).toEqual({ tipo: "esperando", ocupado: false });
      // El retomado consulta a los 0, 2 y 4 s más.
      await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
      expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
      expect(gets(fetchMock)).toBe(3);
    });

    it("tras «Nueva carta», pedir la MISMA carta adopta la espera de fondo", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(200, LISTA_P1));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      act(() => { result.current.reiniciar(); });
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA_B, "es"); });
      expect(posts(fetchMock)).toHaveLength(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(result.current.estado).toEqual({ tipo: "lista", texto: "t", lang: "es", disclaimer: "d" });
    });

    it("al pedir guarda el idioma con el pedido en curso", async () => {
      fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "pt"); });
      expect(pendiente()).toMatchObject({ lang: "pt" });
    });

    it("la misma carta en OTRO idioma no adopta la espera de fondo: pide aparte", async () => {
      fetchMock
        .mockReturnValueOnce(res(202, { estado: "generando" }))
        .mockReturnValueOnce(res(409, { motivo: "usado" }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA, "es"); });
      act(() => { result.current.reiniciar(); });
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA_B, "en"); });
      expect(posts(fetchMock)).toHaveLength(2);
    });

    it("adoptar no depende del orden de las claves de los datos", async () => {
      fetchMock.mockReturnValueOnce(res(202, { estado: "generando" }));
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await result.current.pedir({ date: "A", time: "1" }, CARTA, "es"); });
      act(() => { result.current.reiniciar(); });
      await act(async () => { await result.current.pedir({ time: "1", date: "A" }, CARTA_B, "es"); });
      expect(posts(fetchMock)).toHaveLength(1);
    });

    it("tras adoptar y fallar, «Probar de nuevo» con la carta en pantalla reusa el pedido", async () => {
      const P9 = "00000000-0000-4000-8000-000000000009";
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, pedido: P9, lang: "es", vence: Date.now() + 60_000 }));
      fetchMock
        .mockReturnValueOnce(res(200, { estado: "fallida", pedido: P9 }).then(async (r) => {
          await new Promise((ok) => setTimeout(ok, 10));
          return r;
        }))
        .mockReturnValueOnce(res(202, { estado: "generando" }));
      const { result } = renderHook(() => useLecturaAnonima());
      // Adopta antes de que vuelva el primer sondeo.
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA_B, "es"); });
      await act(async () => { await vi.advanceTimersByTimeAsync(50); });
      expect(result.current.estado).toEqual({ tipo: "fallida" });
      await act(async () => { await result.current.pedir({ date: "A" }, CARTA_B, "es"); });
      expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P9]);
    });

    it("la espera retomada no bloquea pedir de frente otra carta", async () => {
      // El retomado no pasa por `randomUUID`: se le da un id que el mock no repite.
      const P9 = "00000000-0000-4000-8000-000000000009";
      localStorage.setItem("astra-lectura-pedido", JSON.stringify({ ...PEND, pedido: P9, vence: Date.now() + 60_000 }));
      fetchMock.mockImplementation((url: string, init?: { method?: string }) =>
        init?.method === "POST" ? res(409, { motivo: "usado" }) : res(200, { estado: "generando", pedido: P9 }),
      );
      const { result } = renderHook(() => useLecturaAnonima());
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      await act(async () => { await result.current.pedir({ date: "B" }, CARTA_B, "es"); });
      expect(result.current.estado).toEqual({ tipo: "usada" });
      // El 409 de B no pisa ni borra el pedido en curso de A, que sigue de fondo.
      expect(posts(fetchMock).map((b) => b.pedido)).toEqual([P1]);
      expect(pendiente()).toMatchObject({ pedido: P9 });
      const n = gets(fetchMock);
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(gets(fetchMock)).toBeGreaterThan(n);
    });
  });
});
