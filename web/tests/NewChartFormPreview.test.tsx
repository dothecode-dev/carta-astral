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

const CARTA_CON_TEASER = {
  ...CARTA,
  teaser: {
    bloques: [{ cuerpo: "Sun", signo: "Gem", textos: { es: "Párrafo del Sol.", en: "Sun.", pt: "Sol." } }],
    indice: [{ slug: "identidad", titulos: { es: "Identidad", en: "Identity", pt: "Identidade" }, temas: [] }],
    informe: { secciones: 8, palabras: 6200 },
  },
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

  it("manda de dónde llegó la visita junto con la carta", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    const [, init] = fetchMock.mock.calls.find((c) => c[0] === "/api/charts/preview")!;
    expect(JSON.parse(init.body).procedencia).toMatchObject({ zona: expect.any(String) });
  });

  it("calcula contra el preview y no crea ninguna carta", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls).toContain("/api/charts/preview");
    expect(urls).not.toContain("/api/charts");
    expect(screen.getByText(t.previewTitle)).toBeTruthy();
  });

  it("no manda a entrar antes de mostrar la carta", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    expect(push).not.toHaveBeenCalled();
  });

  it("tras el preview mide teaser_visto una sola vez, con la hora y las secciones", async () => {
    track.mockClear();
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    fireEvent.change(screen.getByLabelText(t.time), { target: { value: "19:30" } });
    await completarYEnviar(fetchMock, { ok: true, status: 200, json: async () => CARTA_CON_TEASER });

    const vistos = track.mock.calls.filter((c) => c[0] === "teaser_visto");
    expect(vistos).toEqual([["teaser_visto", { con_hora: true, secciones: 8 }]]);
    expect(screen.getByText("Sol en Géminis")).toBeTruthy();
  });

  it("sin hora de nacimiento teaser_visto lo dice", async () => {
    track.mockClear();
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, { ok: true, status: 200, json: async () => CARTA_CON_TEASER });

    expect(track).toHaveBeenCalledWith("teaser_visto", { con_hora: false, secciones: 8 });
  });

  it("si el backend no manda teaser no mide teaser_visto y la pantalla sigue andando", async () => {
    track.mockClear();
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, CALCULADA);

    expect(track.mock.calls.some((c) => c[0] === "teaser_visto")).toBe(false);
    expect(screen.getByText(t.previewTitle)).toBeTruthy();
  });

  // RF9: una lectura anónima de antes, o un pedido en curso, ni se muestra ni se retoma.
  it("con una lectura anónima guardada no ofrece verla ni pide nada", async () => {
    localStorage.setItem("astra-lectura-anonima", JSON.stringify({
      carta: CARTA, datos: DATOS_GUARDADOS, texto: "guardada", lang: "es", disclaimer: "", vence: Date.now() + 3600_000,
    }));
    localStorage.setItem("astra-lectura-pedido", JSON.stringify({
      pedido: "00000000-0000-4000-8000-0000000000aa", carta: CARTA, datos: DATOS_GUARDADOS, vence: Date.now() + 60_000,
    }));
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(screen.queryByRole("button", { name: /Ver tu lectura de/ })).toBeNull();
    expect(screen.queryByText("guardada")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("el preview nunca llama a /api/lectura-anonima y no ofrece pedirla", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, { ok: true, status: 200, json: async () => CARTA_CON_TEASER });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(fetchMock.mock.calls.map((c) => c[0])).not.toContain("/api/lectura-anonima");
    expect(screen.queryByRole("button", { name: t.previewCta })).toBeNull();
  });

  it("si el techo por IP corta, avisa en vez de quedarse mudo", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} />);
    await completarYEnviar(fetchMock, { ok: false, status: 429, json: async () => ({}) });

    expect(screen.getByRole("alert").textContent).toBe(t.failed);
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
    localStorage.clear();
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
      // El de arriba: los dos abren el mismo pago.
      fireEvent.click(screen.getAllByRole("button", { name: BOTON })[0]!);
    });
  }

  it("abre el checkout anónimo con los datos de la carta, mide y redirige a Stripe", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio="US$ 29" />);
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
      moneda: "usd",
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
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    const antes = fetchMock.mock.calls.length;

    await apretar();
    const boton = screen.getAllByRole("button", { name: dict.precios.abriendo })[0]!;
    await act(async () => {
      fireEvent.click(boton);
    });

    expect(fetchMock.mock.calls.length - antes).toBe(1);
  });

  it("el cupón de 100 % pide entrar con el mail", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ motivo: "requiere_cuenta" }) });

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(t.comprarRequiereCuenta);
    expect(assign).not.toHaveBeenCalled();
  });

  it.each([429, 503, 502])("con %s muestra el texto de error del pago y deja reintentar", async (status) => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({}) });

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(dict.precios.fallo);
    expect((screen.getAllByRole("button", { name: BOTON })[0] as HTMLButtonElement).disabled).toBe(false);
  });

  it("un fallo de red también se avisa", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio="US$ 29" />);
    await completarYEnviar(fetchMock, CALCULADA);
    fetchMock.mockRejectedValueOnce(new Error("red"));

    await apretar();

    expect(screen.getByRole("alert").textContent).toBe(dict.precios.fallo);
  });

  it("sin precio del catálogo el botón de pago sigue, sin precio", async () => {
    render(<NewChartForm moneda="usd" locale="es" dict={dict} precio={null} />);
    await completarYEnviar(fetchMock, CALCULADA);

    expect(screen.getAllByRole("button", { name: dict.newChart.comprarCtaSinPrecio })).toHaveLength(2);
  });
});

describe("con sesión (RF12b)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("no hay vista previa ni botón de pago: se crea la carta directo", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<NewChartForm moneda="usd" locale="es" dict={dict} signedIn precio="US$ 29" />);
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

describe("con sesión, al montar", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    push.mockClear();
    replace.mockClear();
    sessionStorage.clear();
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // El flujo de «carta pendiente» se quitó (W3): ya nadie escribe esa clave,
  // y una vieja que quedara en la pestaña no debe crear nada en la cuenta.
  it("una carta pendiente vieja en la pestaña no crea nada", async () => {
    sessionStorage.setItem(
      "astra-carta-pendiente",
      JSON.stringify({ date: "1976-05-31", lat: -32.9, lng: -60.6, time: null, time_known: false, name: null, place_label: "Rosario" }),
    );

    await act(async () => {
      render(<NewChartForm moneda="usd" locale="es" dict={dict} signedIn />);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText(t.date)).toBeTruthy();
  });

  it("sin nada pendiente muestra el formulario y no crea nada", async () => {
    await act(async () => {
      render(<NewChartForm moneda="usd" locale="es" dict={dict} signedIn />);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText(t.date)).toBeTruthy();
  });
});
