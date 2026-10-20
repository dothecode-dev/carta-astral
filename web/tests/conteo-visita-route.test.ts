import { afterEach, describe, expect, it, vi } from "vitest";

// La ruta que cuenta las visitas no le pasa al backend las de un bot: Googlebot
// ejecuta JavaScript y contaría cada página que rastrea como una visita de EE. UU.

const callApi = vi.fn().mockResolvedValue(null);
vi.mock("@/lib/session", async (original) => ({
  ...(await original<typeof import("@/lib/session")>()),
  callApi: (...args: unknown[]) => callApi(...args),
}));

const { POST } = await import("@/app/api/conteo/visita/route");

function pedido(userAgent: string) {
  return new Request("http://localhost/api/conteo/visita", {
    method: "POST",
    headers: { "content-type": "application/json", "user-agent": userAgent },
    body: JSON.stringify({ seccion: "precios", procedencia: { utm_source: "", gclid: false, referrer: "", zona: "" } }),
  });
}

afterEach(() => callApi.mockClear());

describe("POST /api/conteo/visita", () => {
  it("una persona: va al backend con la sección y la procedencia", async () => {
    const r = await POST(pedido("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1"));

    expect(r.status).toBe(204);
    expect(callApi).toHaveBeenCalledOnce();
    expect(JSON.parse(callApi.mock.calls[0][1].body).seccion).toBe("precios");
  });

  it("un teléfono con «bot» en el nombre de la marca sí cuenta", async () => {
    const r = await POST(pedido("Mozilla/5.0 (Linux; Android 10; CUBOT NOTE 20) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"));

    expect(r.status).toBe(204);
    expect(callApi).toHaveBeenCalledOnce();
  });

  it.each([
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (Linux; Android 6.0.1) Chrome/130 Mobile Safari/537.36 (compatible; Googlebot/2.1)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Mozilla/5.0 (Windows NT 10.0) HeadlessChrome/130.0 Safari/537.36",
    "AdsBot-Google (+http://www.google.com/adsbot.html)",
    "",
  ])("un bot no se cuenta: %s", async (ua) => {
    const r = await POST(pedido(ua));

    expect(r.status).toBe(204);
    expect(callApi).not.toHaveBeenCalled();
  });
});
