import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE } from "@/lib/session";

// Las dos rutas de la tercera puerta de acceso (login por mail): pedir el
// código y canjearlo. El canje comparte `route.ts` con Google/Apple, así que
// acá también se cubre que sumar "email" no rompa esos dos caminos.
//
// Invariante que no se toca: el token de sesión NUNCA vuelve al navegador en
// el cuerpo de la respuesta. Lo pone el servidor en una cookie httpOnly.

type Cookie = { value: string; options?: Record<string, unknown> };
let store: Map<string, Cookie>;

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => store.get(name),
    set: (name: string, value: string, options?: Record<string, unknown>) =>
      store.set(name, { value, options }),
    delete: (name: string) => store.delete(name),
  }),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function pedidoCanje(cuerpo: unknown, headers?: Record<string, string>): Request {
  return new Request("http://x/api/session", { method: "POST", body: JSON.stringify(cuerpo), headers });
}

function pedidoCodigo(cuerpo: unknown, headers?: Record<string, string>): Request {
  return new Request("http://x/api/session/codigo", {
    method: "POST",
    body: JSON.stringify(cuerpo),
    headers,
  });
}

beforeEach(() => {
  store = new Map();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("POST /api/session con provider email (canje del código)", () => {
  it("no filtra el token de sesión al navegador", async () => {
    const { POST } = await import("@/app/api/session/route");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({ token: "secreto-del-backend", derechos: [], account_id: 7, destino: "" }),
      ),
    );

    const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
    const cuerpo = await res.json();

    expect(cuerpo).not.toHaveProperty("token");
    expect(Object.keys(cuerpo).sort()).toEqual(["account_id", "derechos"]);
    expect(JSON.stringify(cuerpo)).not.toContain("secreto-del-backend");
  });

  it("guarda el token en la cookie httpOnly, no en la respuesta", async () => {
    const { POST } = await import("@/app/api/session/route");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ token: "un-token", derechos: [], account_id: 7, destino: "" })),
    );

    await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));

    expect(store.get(SESSION_COOKIE)?.value).toBe("un-token");
    expect(store.get(SESSION_COOKIE)?.options).toMatchObject({ httpOnly: true });
  });

  it("manda email y código al backend, y nada más", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn().mockResolvedValue(
      json({ token: "t", derechos: [], account_id: 1, destino: "" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/email");
    expect(url).not.toContain("/api/auth/email/codigo");
    expect(JSON.parse(init.body)).toEqual({ email: "juan@gmail.com", codigo: "123456" });
  });

  it("rechaza un cuerpo sin código", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza un cuerpo sin email", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCanje({ provider: "email", codigo: "123456" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("traduce el 401 de un código vencido o equivocado", async () => {
    const { POST } = await import("@/app/api/session/route");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "código inválido" }, 401)));

    const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "000000" }));

    expect(res.status).toBe(401);
    expect(store.has(SESSION_COOKIE)).toBe(false);
  });

  it("propaga el 503 cuando falta configuración en el backend", async () => {
    const { POST } = await import("@/app/api/session/route");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "login no disponible" }, 503)));

    const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));

    expect(res.status).toBe(503);
  });

  it("reenvía la IP del visitante al backend (C1): sin esto, el scope auth cuenta por la IP de la web", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn().mockResolvedValue(
      json({ token: "t", derechos: [], account_id: 1, destino: "" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(
      pedidoCanje(
        { provider: "email", email: "juan@gmail.com", codigo: "123456" },
        { "x-forwarded-for": "203.0.113.7" },
      ),
    );

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.7");
  });

  it("sin cabecera de origen en el pedido, no manda x-forwarded-for inventado", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn().mockResolvedValue(
      json({ token: "t", derechos: [], account_id: 1, destino: "" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBeUndefined();
  });

  describe("el destino que vuelve del backend se revalida en la web", () => {
    it("expone un path interno válido", async () => {
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({ token: "t", derechos: [], account_id: 1, destino: "/es/precios" }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo.destino).toBe("/es/precios");
    });

    it("nunca expone un destino absoluto, aunque el backend lo mande", async () => {
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({ token: "t", derechos: [], account_id: 1, destino: "https://malo.example" }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo).not.toHaveProperty("destino");
    });

    it("nunca expone un destino protocol-relative, aunque el backend lo mande", async () => {
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({ token: "t", derechos: [], account_id: 1, destino: "//malo.example" }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo).not.toHaveProperty("destino");
    });

    it("conserva ?comprar= y ?cupon= (I2/RF16): quien venía a comprar no cae en una cuenta vacía", async () => {
      // Simula la vuelta por pestaña nueva (iOS Mail): el `next` original no
      // está, así que lo único que trae de vuelta el pedido de qué comprar es
      // este `destino` que guardó el backend.
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({
            token: "t",
            derechos: [],
            account_id: 1,
            destino: "/es/precios?comprar=informe_natal&cupon=VERANO10",
          }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo.destino).toBe("/es/precios?comprar=informe_natal&cupon=VERANO10");
    });

    it("un `comprar` con forma inválida pegado al destino sigue rechazando todo el destino", async () => {
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({
            token: "t",
            derechos: [],
            account_id: 1,
            destino: "/es/precios?comprar=<script>",
          }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo).not.toHaveProperty("destino");
    });

    it("un `next` con query fuera de la lista cerrada sigue rechazando todo el destino", async () => {
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({
            token: "t",
            derechos: [],
            account_id: 1,
            destino: "/es/otra-cosa?comprar=informe_natal",
          }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo).not.toHaveProperty("destino");
    });

    it("nunca expone un path que no está en la lista cerrada de destinoSeguro", async () => {
      // El destino nace en /entrar, donde ya pasó por destinoSeguro contra la
      // lista cerrada (precios, nueva, cuenta, carta/<uuid>). Si lo que vuelve
      // en el canje no está ahí, el backend cambió o alguien lo manipuló — en
      // los dos casos se descarta, no se acepta por "parecer" un path interno.
      const { POST } = await import("@/app/api/session/route");
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          json({ token: "t", derechos: [], account_id: 1, destino: "/es/otra-cosa" }),
        ),
      );

      const res = await POST(pedidoCanje({ provider: "email", email: "juan@gmail.com", codigo: "123456" }));
      const cuerpo = await res.json();

      expect(cuerpo).not.toHaveProperty("destino");
    });
  });
});

describe("POST /api/session con provider google/apple (sin regresión)", () => {
  it("sigue pidiendo id_token y sigue llamando al mismo endpoint", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn().mockResolvedValue(json({ token: "t", derechos: [], account_id: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCanje({ provider: "google", id_token: "id-token" }));

    expect(res.status).toBe(200);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/google");
  });

  it("google también reenvía la IP del visitante (mismo scope auth)", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn().mockResolvedValue(json({ token: "t", derechos: [], account_id: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    await POST(pedidoCanje({ provider: "google", id_token: "id-token" }, { "x-forwarded-for": "198.51.100.9" }));

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("198.51.100.9");
  });

  it("rechaza google sin id_token", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCanje({ provider: "google" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza un provider que no existe", async () => {
    const { POST } = await import("@/app/api/session/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCanje({ provider: "facebook", id_token: "x" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("POST /api/session/codigo (pedir el código por mail)", () => {
  it("manda email, lang y destino al backend tal cual", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    const fetchMock = vi.fn().mockResolvedValue(json({}, 202));
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCodigo({ email: "juan@gmail.com", lang: "es", destino: "/es/precios" }));

    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({});
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/email/codigo");
    expect(JSON.parse(init.body)).toEqual({ email: "juan@gmail.com", lang: "es", destino: "/es/precios" });
  });

  it("no manda el token de sesión: es un pedido público", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    const fetchMock = vi.fn().mockResolvedValue(json({}, 202));
    vi.stubGlobal("fetch", fetchMock);
    store.set(SESSION_COOKIE, { value: "un-token-de-otra-sesion" });

    await POST(pedidoCodigo({ email: "juan@gmail.com", lang: "es" }));

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("reenvía la IP del visitante al backend (C1)", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    const fetchMock = vi.fn().mockResolvedValue(json({}, 202));
    vi.stubGlobal("fetch", fetchMock);

    await POST(
      pedidoCodigo({ email: "juan@gmail.com", lang: "es" }, { "x-forwarded-for": "203.0.113.7" }),
    );

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["x-forwarded-for"]).toBe("203.0.113.7");
  });

  it("propaga el 429 del backend como 429", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "demasiados pedidos" }, 429)));

    const res = await POST(pedidoCodigo({ email: "juan@gmail.com", lang: "es" }));

    expect(res.status).toBe(429);
  });

  it("propaga el 503 cuando el mail no salió", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "login no disponible" }, 503)));

    const res = await POST(pedidoCodigo({ email: "juan@gmail.com", lang: "es" }));

    expect(res.status).toBe(503);
  });

  it("rechaza un cuerpo sin email, sin llamar al backend", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(pedidoCodigo({ lang: "es" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rechaza un cuerpo que no es JSON", async () => {
    const { POST } = await import("@/app/api/session/codigo/route");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(new Request("http://x/api/session/codigo", { method: "POST", body: "no soy json" }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
