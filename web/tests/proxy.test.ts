import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

// El cartel de mantenimiento decide si el sitio entero responde o no, así que
// lo que más importa acá es cómo falla: un backend que no contesta NO puede
// cerrar producción.
//
// El módulo se importa fresco en cada test a propósito: guarda el estado en una
// variable de módulo (el caché de cinco segundos), y compartirla entre tests
// haría que el primero decidiera por los demás.

const pedir = (pathname = "/es/carta/abc") =>
  ({ nextUrl: { pathname } }) as unknown as NextRequest;

async function cargarProxy() {
  vi.resetModules();
  return (await import("@/proxy")).proxy;
}

const responde = (body: unknown, ok = true) => ({
  ok,
  json: async () => body,
});

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("proxy de mantenimiento", () => {
  it("con el cartel prendido devuelve 503 y no deja pasar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: true })));
    const proxy = await cargarProxy();

    const res = await proxy(pedir());

    expect(res.status).toBe(503);
    expect(await res.text()).toContain("Estamos aceitando el universo");
  });

  it("el cartel habla el idioma de la URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: true })));
    const proxy = await cargarProxy();

    expect(await (await proxy(pedir("/en/cuenta"))).text()).toContain("oiling the universe");
  });

  it("no se guarda en ningún caché: al terminar el deploy hay que ver el sitio", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: true })));
    const proxy = await cargarProxy();

    const res = await proxy(pedir());

    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("retry-after")).toBe("300");
  });

  it("con el cartel apagado deja pasar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: false })));
    const proxy = await cargarProxy();

    expect((await proxy(pedir())).status).toBe(200);
  });

  it("si el backend no contesta, el sitio sigue abierto", async () => {
    // El caso peligroso: fallar al revés convertiría un hipo del backend —o un
    // deploy del propio backend— en una caída total del sitio.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin backend")));
    const proxy = await cargarProxy();

    expect((await proxy(pedir())).status).toBe(200);
  });

  it("si el backend responde mal, el sitio sigue abierto", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({}, false)));
    const proxy = await cargarProxy();

    expect((await proxy(pedir())).status).toBe(200);
  });

  it("no pregunta el estado en cada request", async () => {
    // La doc del proxy avisa que no es lugar para traer datos: sin el caché,
    // cada visita a cada página pagaría una consulta al backend.
    const fetchMock = vi.fn().mockResolvedValue(responde({ mantenimiento: false }));
    vi.stubGlobal("fetch", fetchMock);
    const proxy = await cargarProxy();

    await proxy(pedir());
    await proxy(pedir("/es"));
    await proxy(pedir("/en"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
