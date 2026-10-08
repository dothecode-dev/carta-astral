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

const track = vi.fn();
vi.mock("@/lib/telemetry", () => ({ track: (...a: unknown[]) => track(...a) }));

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

const DATOS_GUARDADOS = {
  name: "Ana", date: "1976-05-31", time: null, time_known: false,
  lat: -32.94682, lng: -60.63932, place_label: "Rosario, Santa Fe, AR",
};

const CALCULADA = { ok: true, status: 200, json: async () => CARTA };

describe("sin cuenta", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    push.mockClear();
    replace.mockClear();
    sessionStorage.clear();
    localStorage.clear();
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

  it("al pedir la lectura la escribe acá, sin ir a entrar", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ estado: "generando" }), { status: 202 }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.previewCta })); });
    expect(push).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/lectura-anonima");
    expect(JSON.parse(init.body)).toMatchObject({ date: "1976-05-31", lang: "es" });
    expect(screen.getByRole("status")).toHaveTextContent(t.lecturaEscribiendo);
  });

  it("con una lectura guardada ofrece verla", async () => {
    localStorage.setItem("astra-lectura-anonima", JSON.stringify({
      carta: CARTA, datos: DATOS_GUARDADOS, texto: "guardada", lang: "es", disclaimer: "", vence: Date.now() + 3600_000,
    }));
    render(<NewChartForm locale="es" dict={dict} />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /Ver tu lectura de/ }));
    expect(screen.getByText("guardada")).toBeInTheDocument();
  });

  /** Un backend de lectura anónima con memoria: el primer pedido se escribe;
   *  cualquier otro mientras tanto es «usado» (C1). `lista()` la termina. */
  function backendDeLectura(fetchMock: ReturnType<typeof vi.fn>) {
    let primero: string | null = null;
    let lista = false;
    fetchMock.mockImplementation((url: string, init?: { method?: string; body?: string }) => {
      const r = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
      if (url !== "/api/lectura-anonima") return Promise.reject(new Error(`inesperado: ${url}`));
      if (init?.method === "POST") {
        const { pedido } = JSON.parse(init.body!) as { pedido: string };
        primero ??= pedido;
        return pedido === primero ? r(202, { estado: "generando" }) : r(409, { motivo: "usado" });
      }
      return lista
        ? r(200, { estado: "lista", texto: "la lectura de Ana", lang: "es", disclaimer: "", pedido: primero })
        : r(200, { estado: "generando", pedido: primero });
    });
    return { lista: () => { lista = true; } };
  }

  // C1 + I1 (final review): pide la de A, vuelve, corrige y pide la de B.
  it("la lectura pedida para A nunca aparece ni se guarda como la de B, y queda guardada con A", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    fireEvent.change(screen.getByLabelText(t.name), { target: { value: "Ana" } });
    await completarYEnviar(fetchMock, CALCULADA);
    const backend = backendDeLectura(fetchMock);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.previewCta })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.navNew })); });

    // Corrige la hora y recalcula: otra carta, en el mismo navegador.
    fireEvent.change(screen.getByLabelText(t.name), { target: { value: "Bea" } });
    fireEvent.change(screen.getByLabelText(t.time), { target: { value: "19:30" } });
    fetchMock.mockResolvedValueOnce(CALCULADA);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.submit })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.previewCta })); });
    expect(screen.getByRole("status")).toHaveTextContent(t.lecturaUsada);

    backend.lista();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(screen.queryByText("la lectura de Ana")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(t.lecturaUsada);
    const guardada = JSON.parse(localStorage.getItem("astra-lectura-anonima")!);
    expect(guardada.texto).toBe("la lectura de Ana");
    expect(guardada.datos).toMatchObject({ name: "Ana", time: null });

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.navNew })); });
    expect(screen.getByRole("button", { name: "Ver tu lectura de Ana" })).toBeInTheDocument();
  });

  it("volver mientras se escribe: la guarda de fondo y ofrece verla sin recargar", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    fireEvent.change(screen.getByLabelText(t.name), { target: { value: "Ana" } });
    await completarYEnviar(fetchMock, CALCULADA);
    const backend = backendDeLectura(fetchMock);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.previewCta })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.navNew })); });
    expect(screen.queryByRole("button", { name: /Ver tu lectura de/ })).toBeNull();

    backend.lista();
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    fireEvent.click(screen.getByRole("button", { name: "Ver tu lectura de Ana" }));
    expect(screen.getByText("la lectura de Ana")).toBeInTheDocument();
  });

  it("después de leerla, al volver ofrece verla otra vez", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    fireEvent.change(screen.getByLabelText(t.name), { target: { value: "Ana" } });
    await completarYEnviar(fetchMock, CALCULADA);
    const backend = backendDeLectura(fetchMock);
    backend.lista();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.previewCta })); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("la lectura de Ana")).toBeInTheDocument();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: t.navNew })); });
    expect(screen.getByRole("button", { name: "Ver tu lectura de Ana" })).toBeInTheDocument();
  });

  it("si el techo por IP corta, avisa en vez de quedarse mudo", async () => {
    render(<NewChartForm locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, { ok: false, status: 429, json: async () => ({}) });

    expect(screen.getByRole("alert").textContent).toBe(t.failed);
  });
});

describe("lectura guardada reabierta", () => {
  it("el botón de comprar funciona: manda lo guardado al checkout anónimo", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    localStorage.clear();
    localStorage.setItem("astra-lectura-anonima", JSON.stringify({
      carta: CARTA, datos: DATOS_GUARDADOS, texto: "guardada", lang: "es", disclaimer: "", vence: Date.now() + 3600_000,
    }));
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /Ver tu lectura de Ana/ }));
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ url: "https://stripe.test/c" }) });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Leer el informe completo · US\$ 29/ }));
    });
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/checkout/anonimo");
    expect(JSON.parse(init.body)).toMatchObject({ ...DATOS_GUARDADOS, locale: "es" });
    expect(assign).toHaveBeenCalledWith("https://stripe.test/c");
    vi.unstubAllGlobals();
  });
});

describe("comprar sin cuenta desde la vista previa", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const assign = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    push.mockClear();
    track.mockClear();
    assign.mockClear();
    sessionStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("location", { ...window.location, assign });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const BOTON = /Leer el informe completo · US\$ 29/;

  async function apretar() {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: BOTON }));
    });
  }

  it("abre el checkout anónimo con los datos de la carta, mide y redirige a Stripe", async () => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ url: "https://stripe.test/c" }) });

    await apretar();

    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toBe("/api/checkout/anonimo");
    expect(JSON.parse(init.body)).toMatchObject({
      date: "1976-05-31",
      lat: ROSARIO.lat,
      lng: ROSARIO.lng,
      locale: "es",
    });
    expect(track).toHaveBeenCalledWith("checkout_iniciado", {
      producto: "informe_natal",
      desde: "carta",
      anonimo: true,
    });
    expect(assign).toHaveBeenCalledWith("https://stripe.test/c");
    expect(push).not.toHaveBeenCalled();
  });

  it("un doble clic abre un solo checkout", async () => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    const antes = fetchMock.mock.calls.length;

    await apretar();
    const boton = screen.getByRole("button", { name: dict.precios.abriendo });
    await act(async () => {
      fireEvent.click(boton);
    });

    expect(fetchMock.mock.calls.length - antes).toBe(1);
  });

  it("el cupón de 100 % pide entrar con el mail", async () => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ motivo: "requiere_cuenta" }) });

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(t.comprarRequiereCuenta);
    expect(assign).not.toHaveBeenCalled();
  });

  it.each([429, 503, 502])("con %s muestra el texto de error del pago y deja reintentar", async (status) => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({}) });

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(dict.precios.fallo);
    expect((screen.getByRole("button", { name: BOTON }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("un fallo de red también se avisa", async () => {
    render(<NewChartForm locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockRejectedValueOnce(new Error("red"));

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(dict.precios.fallo);
  });

  it("sin precio del catálogo no hay botón de pago", async () => {
    render(<NewChartForm locale="es" dict={dict} precio={null} />);
    await completarYEnviar(fetchMock, CALCULADA);

    expect(screen.queryByRole("button", { name: /Leer el informe completo/ })).toBeNull();
  });
});

describe("con sesión (RF12b)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("no hay vista previa ni botón de pago: se crea la carta directo", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<NewChartForm locale="es" dict={dict} signedIn precio="US$ 29" />);
      await completarYEnviar(fetchMock, { ok: true, status: 201, json: async () => ({ id: "abc" }) });

      expect(fetchMock.mock.calls.map((c) => c[0])).toContain("/api/charts");
      expect(fetchMock.mock.calls.map((c) => c[0])).not.toContain("/api/charts/preview");
      expect(screen.queryByRole("button", { name: /Leer el informe completo/ })).toBeNull();
      expect(replace).toHaveBeenCalledWith("/es/carta/abc");
    } finally {
      vi.useRealTimers();
    }
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
