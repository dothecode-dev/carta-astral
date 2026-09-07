import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// La página de precios con `?cupon=`: el precio tachado sale del backend, el
// JSON-LD sigue publicando la lista (Google no indexa una promoción como si
// fuera el precio), y un cupón que no sirve deja los precios de lista con un
// aviso — nunca un descuento inventado.

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (url: string) => {
    throw new Error(`redirect: ${url}`);
  },
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined, set: () => {}, delete: () => {} }),
}));
vi.mock("@/lib/telemetry", () => ({ track: vi.fn() }));

const { default: PreciosPage } = await import("@/app/[locale]/precios/page");

const CATALOGO = {
  productos: [
    { codigo: "informe_natal", precio_centavos: 2900, moneda: "usd", otorga: [{ codigo: "informe_natal", cantidad: 1 }] },
    { codigo: "pack_5_natal", precio_centavos: 12500, moneda: "usd", otorga: [{ codigo: "informe_natal", cantidad: 5 }] },
  ],
};
const CUPON = {
  valido: true, codigo: "PROMO30", porcentaje: 30,
  productos: [{ ...CATALOGO.productos[0], precio_final_centavos: 2030, descuento_centavos: 870 }],
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubBackend(cupon: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => (String(url).includes("/api/cupones/") ? json(cupon) : json(CATALOGO))));
}

async function pagina(query: Record<string, string>) {
  const ui = await PreciosPage({
    params: Promise.resolve({ locale: "es" }),
    searchParams: Promise.resolve(query),
  });
  return render(ui);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
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

describe("/precios?cupon=", () => {
  it("muestra el precio de lista tachado y el final al lado, sólo en lo que el cupón abarca", async () => {
    stubBackend(CUPON);
    const { container } = await pagina({ cupon: "promo30" });

    const tachados = container.querySelectorAll(".precioTachado");
    expect(tachados).toHaveLength(1);
    expect(tachados[0]).toHaveTextContent(/29/);
    expect(screen.getByText(/20,30/)).toBeInTheDocument();
    // El pack no está en el cupón: sigue a lista, sin tachar.
    expect(screen.getByText(/125/)).toBeInTheDocument();
  });

  it("el precio por unidad de un pack se calcula sobre lo que se paga", async () => {
    const pack = { ...CATALOGO.productos[1], precio_final_centavos: 8750, descuento_centavos: 3750 };
    stubBackend({ ...CUPON, productos: [pack] });
    await pagina({ cupon: "PROMO30" });

    // 87,50 / 5, no 125 / 5.
    expect(screen.getByText(/17,50/)).toBeInTheDocument();
    expect(screen.queryByText(/US\$\s?25 cada uno/)).toBeNull();
  });

  it("el JSON-LD sigue publicando el precio de lista", async () => {
    stubBackend(CUPON);
    const { container } = await pagina({ cupon: "PROMO30" });

    const ld = JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld.itemListElement[0].item.offers.price).toBe("29.00");
  });

  it("un cupón que no sirve deja los precios de lista y lo dice", async () => {
    stubBackend({ valido: false, motivo: "agotado" });
    const { container } = await pagina({ cupon: "PROMO30" });

    expect(container.querySelectorAll(".precioTachado")).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent(/agot/i);
  });

  it("si el backend de cupones no responde, precio de lista sin aviso de descuento", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (String(url).includes("/api/cupones/") ? json({}, 500) : json(CATALOGO))));
    const { container } = await pagina({ cupon: "PROMO30" });

    expect(container.querySelectorAll(".precioTachado")).toHaveLength(0);
  });

  it("un cupón con forma inválida ni se consulta", async () => {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(async () => json(CATALOGO));
    vi.stubGlobal("fetch", fetchMock);
    await pagina({ cupon: "promo 30" });

    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/api/cupones/"))).toBe(true);
  });

  it("sin cupón sólo hay una línea, y el campo aparece al tocarla", async () => {
    stubBackend(CUPON);
    await pagina({});

    expect(screen.queryByRole("textbox")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /cupón/i }));
    expect(screen.getByRole("textbox", { name: /cup/i })).toBeInTheDocument();
  });

  it("con cupón válido queda la etiqueta con el código y un «quitar» que vuelve a la lista", async () => {
    stubBackend(CUPON);
    await pagina({ cupon: "PROMO30" });

    expect(screen.getByRole("status")).toHaveTextContent(/PROMO30/);
    expect(screen.getByRole("status")).toHaveTextContent(/30/);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("link", { name: /quitar/i })).toHaveAttribute("href", "/es/precios");
  });

  it("con cupón rechazado el campo queda abierto con el código escrito", async () => {
    stubBackend({ valido: false, motivo: "vencido" });
    await pagina({ cupon: "PROMO30" });

    expect(screen.getByRole("textbox")).toHaveValue("PROMO30");
  });
});
