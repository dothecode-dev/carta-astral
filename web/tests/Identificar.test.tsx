import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Identificar } from "@/components/Identificar";

// Por qué existe este componente, con evidencia: el 08-09-2026 la primera
// persona que compró apareció partida en DOS personas de PostHog. Hizo su carta
// y leyó su lectura breve en el iPhone (donde sí hubo login), y volvió veinte
// minutos después desde otra computadora, con la cookie de sesión todavía viva,
// a aplicar el cupón y pagar. Ese segundo navegador nunca pasó por el login, y
// `identificar()` sólo se llamaba desde `GoogleSignIn`: navegó anónimo.
//
// Consecuencia medida: el `checkout_iniciado` quedó en una persona y la
// `compra_completada` en otra, así que el embudo secuencial por unique users
// marca cero compras aunque haya compras.

const identificar = vi.fn();
vi.mock("@/lib/telemetry", () => ({
  identificar: (id: number | string) => identificar(id),
}));

afterEach(() => {
  identificar.mockClear();
});

describe("Identificar", () => {
  it("ata los eventos a la cuenta al cargar una página con sesión", () => {
    render(<Identificar accountId={42} />);

    expect(identificar).toHaveBeenCalledWith(42);
  });

  it("no identifica dos veces por la misma cuenta en un mismo render", () => {
    const { rerender } = render(<Identificar accountId={42} />);
    rerender(<Identificar accountId={42} />);

    expect(identificar).toHaveBeenCalledTimes(1);
  });

  it("vuelve a identificar si cambia la cuenta", () => {
    const { rerender } = render(<Identificar accountId={42} />);
    rerender(<Identificar accountId={7} />);

    expect(identificar).toHaveBeenNthCalledWith(2, 7);
  });

  it("no identifica a nadie sin id", () => {
    render(<Identificar accountId={undefined} />);

    expect(identificar).not.toHaveBeenCalled();
  });
});
