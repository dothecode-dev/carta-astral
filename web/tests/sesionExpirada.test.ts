import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Una cookie de sesión que el backend ya no reconoce —sesión vencida, cuenta
// borrada, base purgada— dejaba al usuario dando vueltas entre /cuenta y
// /entrar con la pantalla en blanco: /cuenta veía la cookie, recibía 401 y
// mandaba a /entrar; /entrar veía la misma cookie y mandaba de vuelta a
// /cuenta, sin preguntarle nunca al backend si el token servía.
//
// Las dos mitades del arreglo se prueban acá: /entrar sólo redirige cuando la
// sesión está viva de verdad, y las páginas con sesión pasan por el handler
// que borra la cookie muerta (un Server Component puede leer cookies, pero
// sólo un Route Handler puede borrarlas).

const { RedirectError, NotFoundError } = vi.hoisted(() => ({
  RedirectError: class RedirectError extends Error {
    constructor(readonly url: string) {
      super(`redirect: ${url}`);
    }
  },
  NotFoundError: class NotFoundError extends Error {},
}));

// El redirect() de Next corta la ejecución lanzando: acá se imita para poder
// afirmar que una página NO redirigió sin que el test siga renderizando.
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectError(url);
  },
  notFound: () => {
    throw new NotFoundError();
  },
}));

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

const { default: SignInPage } = await import("@/app/[locale]/entrar/page");
const { default: AccountPage } = await import("@/app/[locale]/cuenta/page");
const { GET: expiradaGet } = await import("@/app/api/session/expirada/route");
const { SESSION_COOKIE, RUTA_SESION_EXPIRADA } = await import("@/lib/session");

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const params = { params: Promise.resolve({ locale: "es" }) };
// Next siempre le pasa los dos a una página; el de la cuenta no los usa.
const sinQuery = { ...params, searchParams: Promise.resolve({}) };

/** Corre la página y devuelve a dónde redirigió, o null si renderizó. */
async function destinoDe(page: () => Promise<unknown>): Promise<string | null> {
  try {
    await page();
    return null;
  } catch (error) {
    if (error instanceof RedirectError) return error.url;
    throw error;
  }
}

beforeEach(() => {
  store = new Map([[SESSION_COOKIE, { value: "token-que-el-backend-ya-no-conoce" }]]);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("/entrar con una cookie que ya no vale", () => {
  it("muestra el login en vez de rebotar a /cuenta", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "sin sesión" }, 401)));

    expect(await destinoDe(() => SignInPage(sinQuery))).toBeNull();
  });

  it("tampoco rebota si el backend está caído: un 500 no prueba que haya sesión", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "boom" }, 500)));

    expect(await destinoDe(() => SignInPage(sinQuery))).toBeNull();
  });

  it("tampoco rebota si el backend no responde", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    expect(await destinoDe(() => SignInPage(sinQuery))).toBeNull();
  });
});

describe("/entrar con una sesión viva", () => {
  it("sigue mandando a /cuenta a quien ya entró", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ free_credits: 3, paid_credits: 0, account_id: 1 })),
    );

    expect(await destinoDe(() => SignInPage(sinQuery))).toBe("/es/cuenta");
  });

  it("vuelve al lugar del que vino, con la compra que traía", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ free_credits: 3, paid_credits: 0, account_id: 1 })),
    );

    const destino = await destinoDe(() =>
      SignInPage({
        ...params,
        searchParams: Promise.resolve({ next: "/es/precios", comprar: "pack_5_natal" }),
      }),
    );

    expect(destino).toBe("/es/precios?comprar=pack_5_natal");
  });

  // El `next` lo escribe cualquiera que arme un enlace: si se usara tal cual,
  // el sitio serviría para depositar a alguien recién autenticado en un
  // dominio ajeno.
  it("ignora un next que apunte afuera del sitio", async () => {
    // Una Response por llamada: el cuerpo de una sola se consume en la primera
    // y las demás verían una sesión caída en vez de lo que el test prueba.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ free_credits: 3, paid_credits: 0, account_id: 1 })),
    );

    for (const next of ["https://evil.com", "//evil.com", "/es/precios?x=1", "/en/cuenta"]) {
      expect(
        await destinoDe(() =>
          SignInPage({ ...params, searchParams: Promise.resolve({ next }) }),
        ),
      ).toBe("/es/cuenta");
    }
  });

  it("sin cookie no le pregunta nada al backend", async () => {
    store.clear();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(await destinoDe(() => SignInPage(sinQuery))).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("/cuenta cuando el backend rechaza la sesión", () => {
  it("pasa por el handler que borra la cookie, no directo a /entrar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "sin sesión" }, 401)));

    expect(await destinoDe(() => AccountPage(params))).toBe(RUTA_SESION_EXPIRADA("es"));
  });

  it("sin cookie va derecho a /entrar: no hay nada que limpiar", async () => {
    store.clear();
    vi.stubGlobal("fetch", vi.fn());

    expect(await destinoDe(() => AccountPage(params))).toBe("/es/entrar");
  });
});

describe("GET /api/session/expirada", () => {
  it("borra la cookie muerta y manda a /entrar", async () => {
    const res = await expiradaGet(new Request("https://astraguia.com/api/session/expirada?locale=es"));

    expect(store.has(SESSION_COOKIE)).toBe(false);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("/es/entrar");
  });

  it("respeta el idioma en el que venía navegando", async () => {
    const res = await expiradaGet(new Request("https://astraguia.com/api/session/expirada?locale=pt"));

    expect(res.headers.get("location")).toBe("/pt/entrar");
  });

  it("un locale inventado cae al idioma por defecto y nunca a un sitio ajeno", async () => {
    const res = await expiradaGet(
      new Request("https://astraguia.com/api/session/expirada?locale=https://evil.example/x"),
    );

    expect(store.has(SESSION_COOKIE)).toBe(false);
    expect(res.headers.get("location")).toBe("/es/entrar");
  });

  it("el destino es relativo: detrás del proxy, request.url es la del contenedor", async () => {
    // En producción `new URL(path, request.url)` armaba
    // https://0.0.0.0:3000/es/entrar y el navegador no llegaba a ninguna parte.
    const res = await expiradaGet(new Request("http://0.0.0.0:3000/api/session/expirada?locale=es"));

    expect(res.headers.get("location")).toBe("/es/entrar");
  });

  it("sin cookie tampoco falla: entrar a la ruta a mano es inofensivo", async () => {
    store.clear();

    const res = await expiradaGet(new Request("https://astraguia.com/api/session/expirada"));

    expect(res.headers.get("location")).toBe("/es/entrar");
  });
});
