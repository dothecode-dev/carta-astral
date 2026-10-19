import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompraPage from "@/app/[locale]/compra/page";
import { SESSION_COOKIE } from "@/lib/session";

// /compra decide quién maneja la vuelta del pago (RF14): la cookie del nonce
// de ESE checkout manda, haya sesión o no —y aunque la sesión sea de otra
// cuenta—. Sin esa cookie, el flujo de siempre: con sesión se espera la
// confirmación; sin sesión, a entrar.

let store: Map<string, { value: string }>;

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => store.get(name), has: (name: string) => store.has(name) }),
  headers: async () => new Headers(),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (url: string) => {
    throw new Error(`redirect: ${url}`);
  },
}));
vi.mock("@/components/Nav", () => ({
  Nav: ({ signedIn }: { signedIn?: boolean }) => <nav data-testid="nav" data-signed-in={String(!!signedIn)} />,
}));
vi.mock("@/components/Footer", () => ({ Footer: () => <footer /> }));
vi.mock("@/components/CompraEspera", () => ({
  CompraEspera: ({ checkoutId }: { checkoutId: string }) => <div data-testid="espera">{checkoutId}</div>,
}));
vi.mock("@/components/CanjeCompra", () => ({
  CanjeCompra: ({ checkoutId }: { checkoutId: string }) => <div data-testid="canje">{checkoutId}</div>,
}));

const CHECKOUT = "cs_test_a1B2";
const NONCE = `astra_compra_${CHECKOUT}`;

const props = (query: Record<string, string>, locale = "es") => ({
  params: Promise.resolve({ locale }),
  searchParams: Promise.resolve(query),
});

beforeEach(() => {
  store = new Map();
});

describe("/compra", () => {
  it("con la cookie del nonce y sin sesión: canjea", async () => {
    store.set(NONCE, { value: "n" });

    render(await CompraPage(props({ checkout_id: CHECKOUT })));

    expect(screen.getByTestId("canje")).toHaveTextContent(CHECKOUT);
    expect(screen.queryByTestId("espera")).toBeNull();
    expect(screen.getByTestId("nav")).toHaveAttribute("data-signed-in", "false");
  });

  it("con la cookie del nonce y la sesión de otra cuenta: canjea igual", async () => {
    store.set(NONCE, { value: "n" });
    store.set(SESSION_COOKIE, { value: "token-de-otro" });

    render(await CompraPage(props({ checkout_id: CHECKOUT })));

    expect(screen.getByTestId("canje")).toBeInTheDocument();
    expect(screen.queryByTestId("espera")).toBeNull();
  });

  it("acepta también `session_id`, el nombre de los ejemplos de Stripe", async () => {
    store.set(NONCE, { value: "n" });

    render(await CompraPage(props({ session_id: CHECKOUT })));

    expect(screen.getByTestId("canje")).toHaveTextContent(CHECKOUT);
  });

  it("sin la cookie y con sesión: espera la confirmación como siempre", async () => {
    store.set(SESSION_COOKIE, { value: "t" });

    render(await CompraPage(props({ checkout_id: CHECKOUT })));

    expect(screen.getByTestId("espera")).toHaveTextContent(CHECKOUT);
    expect(screen.queryByTestId("canje")).toBeNull();
  });

  it("sin la cookie y sin sesión: a entrar", async () => {
    await expect(CompraPage(props({ checkout_id: CHECKOUT }))).rejects.toThrow("redirect: /es/entrar");
  });

  it("la cookie de OTRO checkout no sirve para este", async () => {
    store.set("astra_compra_cs_test_otro", { value: "n" });

    await expect(CompraPage(props({ checkout_id: CHECKOUT }))).rejects.toThrow("redirect: /es/entrar");
  });

  it("un checkout_id con forma rara no busca cookie", async () => {
    store.set("astra_compra_x", { value: "n" });

    await expect(CompraPage(props({ checkout_id: "x" }))).rejects.toThrow("redirect: /es/entrar");
  });

  // Medido el 19-10-2026 contra el sandbox: quien vuelve de Mercado Pago sin
  // pagar («Volver a la tienda») trae `collection_status=null&status=null`.
  // Antes la página le decía «Listo, gracias. Estamos confirmando tu pago».
  describe("vuelta de Mercado Pago sin pago", () => {
    const MP = "mp_" + "ab".repeat(16);
    const VOLVIO = { checkout_id: MP, collection_status: "null", status: "null", payment_id: "null" };

    it.each(["null", "rejected", "cancelled"])("con collection_status=%s dice que no se cobró, sin esperar", async (estado) => {
      store.set(`astra_compra_${MP}`, { value: "n" });

      render(await CompraPage(props({ ...VOLVIO, collection_status: estado })));

      expect(screen.getByRole("heading", { name: "El pago no se completó" })).toBeInTheDocument();
      expect(screen.queryByTestId("canje")).toBeNull();
      expect(screen.queryByTestId("espera")).toBeNull();
    });

    it("sin sesión ofrece volver a la carta; con sesión, ir a la cuenta", async () => {
      const { unmount } = render(await CompraPage(props(VOLVIO)));
      expect(screen.getByRole("link", { name: /carta/i })).toHaveAttribute("href", "/es/nueva");
      unmount();

      store.set(SESSION_COOKIE, { value: "t" });
      render(await CompraPage(props(VOLVIO)));
      expect(screen.getByRole("link", { name: "Ir a mi cuenta" })).toHaveAttribute("href", "/es/cuenta");
    });

    it.each(["approved", "pending", "in_process"])("con collection_status=%s espera como siempre", async (estado) => {
      store.set(`astra_compra_${MP}`, { value: "n" });

      render(await CompraPage(props({ ...VOLVIO, collection_status: estado })));

      expect(screen.getByTestId("canje")).toHaveTextContent(MP);
    });

    it("un checkout de Stripe no mira collection_status", async () => {
      store.set(NONCE, { value: "n" });

      render(await CompraPage(props({ checkout_id: CHECKOUT, collection_status: "null" })));

      expect(screen.getByTestId("canje")).toBeInTheDocument();
    });
  });
});
