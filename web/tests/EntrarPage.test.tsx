import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// T12: se montan dos puertas en /entrar, Google arriba y mail abajo (Ruling 5).
// Lo que prueban estos tests es la COMPOSICIÓN de la página, no el trato de
// cada puerta con su backend — eso ya está cubierto en GoogleSignIn.test.tsx y
// EntrarPorMail.test.tsx. Por eso las dos puertas se mockean acá: lo que
// importa es en qué orden se montan y qué `next` reciben, no cómo funcionan
// por dentro.
//
// Ruling 21: el test que traía el plan ("nombra la carta de la que viene la
// persona") pasa hoy sin escribir una línea de código —el copy no ramifica
// por destino—, así que no se escribe. En su lugar, lo propio de esta tarea:
// el orden, que las dos puertas reciban el mismo destino (`volverA`, que
// combina `next` con `comprar` y `cupon`), y que una sesión viva siga
// redirigiendo antes de renderizar nada, respetando ese mismo destino.

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (url: string) => {
    throw new Error(`redirect: ${url}`);
  },
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/session", () => ({ sessionIsLive: vi.fn() }));
vi.mock("@/lib/telemetry", () => ({ track: vi.fn(), identificar: vi.fn() }));

vi.mock("@/components/GoogleSignIn", () => ({
  GoogleSignIn: ({ next }: { next?: string | null }) => (
    <div data-testid="puerta-google">{next ?? ""}</div>
  ),
}));
vi.mock("@/components/EntrarPorMail", () => ({
  EntrarPorMail: ({ next }: { next?: string | null }) => (
    <div data-testid="puerta-mail">{next ?? ""}</div>
  ),
}));

const { sessionIsLive } = await import("@/lib/session");
const { default: SignInPage } = await import("@/app/[locale]/entrar/page");

const params = { params: Promise.resolve({ locale: "es" }) };

async function pagina(query: Record<string, string> = {}) {
  const ui = await SignInPage({ ...params, searchParams: Promise.resolve(query) });
  return render(ui);
}

beforeEach(() => {
  vi.mocked(sessionIsLive).mockResolvedValue(false);
  // El Nav trae el interruptor de tema, que consulta matchMedia; jsdom no lo tiene.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("/entrar monta las dos puertas, Google primero", () => {
  it("las renderiza en ese orden: google, después mail", async () => {
    const { container } = await pagina();

    const puertas = [...container.querySelectorAll("[data-testid^='puerta-']")].map((el) =>
      el.getAttribute("data-testid"),
    );
    expect(puertas).toEqual(["puerta-google", "puerta-mail"]);
  });

  it("las dos reciben el mismo destino (next + comprar + cupon), no dos next distintos", async () => {
    await pagina({ next: "/es/precios", comprar: "pack_5_natal", cupon: "promo30" });

    const esperado = "/es/precios?comprar=pack_5_natal&cupon=PROMO30";
    expect(screen.getByTestId("puerta-google")).toHaveTextContent(esperado);
    expect(screen.getByTestId("puerta-mail")).toHaveTextContent(esperado);
  });

  it("sin next las dos quedan sin destino, ninguna se queda con uno y la otra no", async () => {
    await pagina();

    expect(screen.getByTestId("puerta-google")).toHaveTextContent("");
    expect(screen.getByTestId("puerta-mail")).toHaveTextContent("");
  });
});

describe("/entrar con una sesión viva", () => {
  it("redirige antes de renderizar nada, al destino armado con los extras de compra", async () => {
    vi.mocked(sessionIsLive).mockResolvedValue(true);

    await expect(
      SignInPage({
        ...params,
        searchParams: Promise.resolve({ next: "/es/precios", comprar: "pack_5_natal" }),
      }),
    ).rejects.toThrow("redirect: /es/precios?comprar=pack_5_natal");
  });

  it("sin destino pedido, manda a /cuenta", async () => {
    vi.mocked(sessionIsLive).mockResolvedValue(true);

    await expect(
      SignInPage({ ...params, searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("redirect: /es/cuenta");
  });
});
