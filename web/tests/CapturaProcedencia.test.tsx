import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { _reiniciarProcedencia } from "@/lib/procedencia";

// Cada página abierta suma una visita en el servidor, sin cookies (20-10-2026):
// la sección de una lista cerrada, el canal y la zona; el país lo saca el
// servidor de la IP.

let ruta = "/es/precios";
vi.mock("next/navigation", () => ({ usePathname: () => ruta }));

const { CapturaProcedencia } = await import("@/components/CapturaProcedencia");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  _reiniciarProcedencia();
});

function visitas(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls
    .filter(([url]) => url === "/api/conteo/visita")
    .map(([, init]) => JSON.parse((init as RequestInit).body as string));
}

describe("CapturaProcedencia cuenta las visitas", () => {
  it("al abrir una página manda su sección y la procedencia, sin la ruta", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    ruta = "/es/carta/4712beb7-b86c-44bb-90ca-2b576edbf553";

    render(<CapturaProcedencia />);

    const [visita] = visitas(fetchMock);
    expect(visita.seccion).toBe("carta");
    expect(Object.keys(visita.procedencia).sort()).toEqual(["gclid", "referrer", "utm_source", "zona"]);
    expect(JSON.stringify(visita)).not.toContain("4712beb7");
  });

  it("una navegación interna cuenta otra visita; volver a dibujar la misma página, no", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    ruta = "/es";
    const { rerender } = render(<CapturaProcedencia />);
    rerender(<CapturaProcedencia />);

    ruta = "/es/nueva";
    rerender(<CapturaProcedencia />);

    expect(visitas(fetchMock).map((v) => v.seccion)).toEqual(["inicio", "nueva"]);
  });

  it("si contar falla, no rompe nada", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin red")));
    ruta = "/es";

    expect(() => render(<CapturaProcedencia />)).not.toThrow();
  });
});
