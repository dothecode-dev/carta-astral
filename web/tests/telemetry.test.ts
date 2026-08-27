import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Las dos invariantes que sostienen la promesa de la política de privacidad:
// sin token no se mide nada, y sin consentimiento explícito tampoco. La segunda
// no es una preferencia de producto — es lo que la web declara en es/en/pt y lo
// que el RGPD exige para tener analítica con usuarios en Europa.
//
// El módulo lee el token al importarse, así que cada caso necesita su propio
// import: de ahí `resetModules` y los `await import` dentro de cada test.

const CLAVE = "NEXT_PUBLIC_POSTHOG_KEY";

/** El SDK espiado. Que `init` no se llame es la prueba de que no se midió. */
const init = vi.fn();
const capture = vi.fn();
const optIn = vi.fn();
const optOut = vi.fn();
const reset = vi.fn();
/** El orden de apagado importa y hay un test que lo mira. */
const orden: string[] = [];

vi.mock("posthog-js", () => ({
  default: {
    init,
    capture,
    identify: vi.fn(),
    opt_in_capturing: () => optIn(),
    opt_out_capturing: () => void (optOut(), orden.push("opt_out")),
    reset: () => void (reset(), orden.push("reset")),
  },
}));

let guardado: Map<string, string>;

beforeEach(() => {
  vi.resetModules();
  init.mockClear();
  capture.mockClear();
  optIn.mockClear();
  optOut.mockClear();
  reset.mockClear();
  orden.length = 0;
  guardado = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => guardado.get(k) ?? null,
    setItem: (k: string, v: string) => void guardado.set(k, v),
    removeItem: (k: string) => void guardado.delete(k),
  });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("sin token de PostHog", () => {
  // El build de CI corre dos veces, una con todas las variables vacías, porque
  // un ARG ausente en el Dockerfile deja la variable en "" y eso ya rompió un
  // deploy. Con la variable vacía la telemetría tiene que ser inofensiva.
  beforeEach(() => vi.stubEnv(CLAVE, ""));

  it("no inicializa el SDK aunque haya consentimiento", async () => {
    guardado.set("astra-consent", "si");
    const { activar, activarSiConsintio } = await import("@/lib/telemetry");

    await activarSiConsintio();
    await activar();

    expect(init).not.toHaveBeenCalled();
  });

  it("track no explota ni manda nada", async () => {
    const { track } = await import("@/lib/telemetry");

    expect(() => track("carta_creada", {})).not.toThrow();
    expect(capture).not.toHaveBeenCalled();
  });
});

describe("con token", () => {
  beforeEach(() => vi.stubEnv(CLAVE, "phc_de_prueba"));

  it("sin decisión guardada no arranca: quien no dijo nada no consintió", async () => {
    const { activarSiConsintio } = await import("@/lib/telemetry");

    await activarSiConsintio();

    expect(init).not.toHaveBeenCalled();
  });

  it("con el rechazo guardado tampoco arranca", async () => {
    guardado.set("astra-consent", "no");
    const { activarSiConsintio } = await import("@/lib/telemetry");

    await activarSiConsintio();

    expect(init).not.toHaveBeenCalled();
  });

  it("con el consentimiento guardado arranca sin autocapture ni grabación", async () => {
    guardado.set("astra-consent", "si");
    const { activarSiConsintio } = await import("@/lib/telemetry");

    await activarSiConsintio();

    expect(init).toHaveBeenCalledOnce();
    const [token, opciones] = init.mock.calls[0];
    expect(token).toBe("phc_de_prueba");
    // Autocapture mandaría el texto del elemento clickeado: en /nueva eso es el
    // lugar de nacimiento y en /carta el nombre.
    expect(opciones.autocapture).toBe(false);
    expect(opciones.disable_session_recording).toBe(true);
    expect(opciones.capture_pageview).toBe(false);
    // El pedido de flags escapa a `before_send` y manda `$initial_current_url`
    // con el uuid de la carta crudo. No usamos flags: se apaga entero.
    expect(opciones.advanced_disable_flags).toBe(true);
  });

  it("revocar apaga en el orden correcto: reset() y recién después opt_out()", async () => {
    // Al revés el opt-out se deshace solo: `reset()` limpia el consentimiento y
    // devuelve la instancia a su estado por defecto, que acá es "opted in".
    guardado.set("astra-consent", "si");
    const { activarSiConsintio, desactivar } = await import("@/lib/telemetry");
    await activarSiConsintio();

    desactivar();

    expect(orden).toEqual(["reset", "opt_out"]);
  });

  it("volver a aceptar después de revocar vuelve a medir, sin recargar la página", async () => {
    // Es el camino de revocación que exige el RGPD: aceptar, retirar el
    // consentimiento desde el pie y volver a aceptar. Antes quedaba mudo hasta
    // recargar, porque la promesa de carga no se limpiaba.
    guardado.set("astra-consent", "si");
    const { activar, activarSiConsintio, desactivar, track } = await import("@/lib/telemetry");
    await activarSiConsintio();

    desactivar();
    await activar();
    track("carta_creada", {});

    // `init` corre una vez sola —el SDK es un singleton—, así que lo que
    // rehabilita la captura es `opt_in_capturing`.
    expect(init).toHaveBeenCalledOnce();
    expect(optIn).toHaveBeenCalledOnce();
    expect(capture).toHaveBeenCalledWith("carta_creada", {});
  });

  it("no manda eventos mientras no se haya activado", async () => {
    const { track } = await import("@/lib/telemetry");

    track("carta_creada", {});

    expect(capture).not.toHaveBeenCalled();
  });
});

describe("normalización de rutas", () => {
  // PostHog agrega $current_url por su cuenta. En /carta/<uuid> eso lleva el
  // identificador de la carta adentro, que señala a una persona igual que un
  // nombre.
  it("reemplaza el uuid de una carta por [id]", async () => {
    vi.stubEnv(CLAVE, "phc_de_prueba");
    const { normalizarRuta } = await import("@/lib/telemetry");

    expect(normalizarRuta("/es/carta/3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b")).toBe("/es/carta/[id]");
  });

  it("deja intacta una ruta sin uuid", async () => {
    vi.stubEnv(CLAVE, "phc_de_prueba");
    const { normalizarRuta } = await import("@/lib/telemetry");

    expect(normalizarRuta("/es/notas/mercurio-retrogrado")).toBe("/es/notas/mercurio-retrogrado");
  });
});

describe("página vista", () => {
  beforeEach(() => vi.stubEnv(CLAVE, "phc_de_prueba"));

  it("separa el idioma del camino para que /es/nueva y /en/nueva sean la misma página", async () => {
    guardado.set("astra-consent", "si");
    const { activarSiConsintio, capturarPagina } = await import("@/lib/telemetry");
    await activarSiConsintio();

    capturarPagina("https://astraguia.com/en/nueva");

    expect(capture).toHaveBeenCalledWith("pagina_vista", { locale: "en", ruta: "/nueva" });
  });

  it("normaliza el uuid de la carta", async () => {
    guardado.set("astra-consent", "si");
    const { activarSiConsintio, capturarPagina } = await import("@/lib/telemetry");
    await activarSiConsintio();

    capturarPagina("https://astraguia.com/es/carta/3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b");

    expect(capture).toHaveBeenCalledWith("pagina_vista", { locale: "es", ruta: "/carta/[id]" });
  });

  it("sin consentimiento no cuenta la visita", async () => {
    const { capturarPagina } = await import("@/lib/telemetry");

    capturarPagina("https://astraguia.com/es");

    expect(capture).not.toHaveBeenCalled();
  });
});
