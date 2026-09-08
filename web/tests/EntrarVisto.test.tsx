import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EntrarVisto } from "@/components/EntrarVisto";
import { track as trackReal } from "@/lib/telemetry";

// Sin esto, alguien que llega a /entrar y se da vuelta antes de intentar el
// login no deja ningún rastro: el 08-09-2026 tres de seis visitas se
// devolvieron en segundos y nadie supo qué vieron. Se dispara al MONTAR,
// nunca al loguearse: eso ya lo mide `login` en GoogleSignIn.

vi.mock("@/lib/telemetry", () => ({ track: vi.fn() }));
const track = vi.mocked(trackReal);

beforeEach(() => {
  track.mockClear();
});

describe("EntrarVisto", () => {
  it("avisa que alguien llegó a /entrar, con la ruta de destino", () => {
    render(<EntrarVisto next="/es/precios" />);

    expect(track).toHaveBeenCalledWith("entrar_visto", { next: "/es/precios" });
  });

  it("no manda datos personales: sólo la ruta, y nada si no había destino", () => {
    render(<EntrarVisto next={null} />);

    expect(track).toHaveBeenCalledWith("entrar_visto", {});
  });

  it("no renderiza nada visible", () => {
    const { container } = render(<EntrarVisto next={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
