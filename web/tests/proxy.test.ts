import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

// El cartel de mantenimiento decide si el sitio entero responde o no, así que
// lo que más importa acá es cómo falla: un backend que no contesta NO puede
// cerrar producción.
//
// El módulo se importa fresco en cada test a propósito: guarda el estado en una
// variable de módulo (el caché de cinco segundos), y compartirla entre tests
// haría que el primero decidiera por los demás.

// `nextUrl` es una URL de verdad y no un objeto plano: el redirect de la raíz
// la clona y le cambia el pathname, y con un mock plano el test pasaría
// mientras producción devuelve 500 por URL inválida. Pasó exactamente eso.
const pedir = (
  pathname = "/es/carta/abc",
  acceptLanguage: string | null = null,
  origen = "https://astraguia.com",
) =>
  ({
    nextUrl: new URL(pathname, origen),
    headers: { get: (nombre: string) => (nombre === "accept-language" ? acceptLanguage : null) },
  }) as unknown as NextRequest;

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

  // El 03-09-2026 el cartel tumbó su propio deploy: `/healthz` caía en el 503,
  // Coolify lo leyó como contenedor enfermo y revirtió al viejo. La web se
  // quedó dos commits atrás mientras `make deploy` decía que todo bien. Un
  // liveness dice si el proceso está vivo; no puede depender de un flag de
  // negocio que justamente se prende durante el deploy.
  it("el liveness contesta aunque el cartel esté puesto", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: true })));
    const proxy = await cargarProxy();

    const res = await proxy(pedir("/healthz"));

    expect(res.status).not.toBe(503);
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

describe("la raíz elige idioma", () => {
  const abierto = () =>
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: false })));

  it("manda al idioma que pide el navegador", async () => {
    abierto();
    const proxy = await cargarProxy();

    const res = await proxy(pedir("/", "pt-BR,pt;q=0.9,en;q=0.8"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("https://astraguia.com/pt");
  });

  it("sin cabecera, o con un idioma que no tenemos, cae en español", async () => {
    abierto();
    const proxy = await cargarProxy();

    expect((await proxy(pedir("/", null))).headers.get("location")).toBe("https://astraguia.com/es");
    expect((await proxy(pedir("/", "de-DE,de;q=0.9"))).headers.get("location")).toBe(
      "https://astraguia.com/es",
    );
  });

  it("el redirect conserva el host por el que entró el visitante", async () => {
    // La trampa de `/entrar`: armar la URL sobre `request.url` hace que detrás
    // de Traefik el Location salga apuntando al contenedor
    // (`https://0.0.0.0:3000/...`) y el navegador no llegue a ningún lado.
    abierto();
    const proxy = await cargarProxy();

    const location = (await proxy(pedir("/", "en", "https://www.astraguia.com"))).headers.get(
      "location",
    );

    expect(location).toBe("https://www.astraguia.com/en");
  });

  it("avisa que la respuesta depende del idioma", async () => {
    // Sin `Vary`, un CDN le sirve a todo el mundo el idioma del primero que pasó.
    abierto();
    const proxy = await cargarProxy();

    expect((await proxy(pedir("/", "pt"))).headers.get("vary")).toBe("Accept-Language");
  });

  it("en mantenimiento la raíz muestra el cartel, no el redirect", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responde({ mantenimiento: true })));
    const proxy = await cargarProxy();

    const res = await proxy(pedir("/", "pt-BR"));

    expect(res.status).toBe(503);
  });

  it("las demás rutas siguen pasando de largo", async () => {
    abierto();
    const proxy = await cargarProxy();

    expect((await proxy(pedir("/es/cuenta", "pt-BR"))).status).toBe(200);
  });
});
