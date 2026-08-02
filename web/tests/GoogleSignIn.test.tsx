import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GoogleSignIn } from "@/components/GoogleSignIn";
import { getDict } from "@/lib/i18n";

// Lo que se prueba acá es el trato con el id_token que devuelve Google: se
// manda a /api/session y nada más. Si el canje falla, la persona tiene que
// enterarse en vez de quedar mirando un botón que no hace nada.

const replace = vi.fn();
const refresh = vi.fn();
// El router tiene que ser el mismo objeto entre renders, como el de Next: si
// cambia de identidad, el efecto que monta el botón de Google se vuelve a
// ejecutar y pisa lo que se haya mostrado.
const router = { replace, refresh };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const dict = getDict("es");
const labels = {
  loading: dict.auth.loading,
  blocked: dict.auth.blocked,
  failed: dict.auth.failed,
};

/** Guarda el callback que el componente le pasa a Google para dispararlo a mano. */
let onCredential: ((r: { credential?: string }) => void) | null = null;

function fakeGoogle() {
  return {
    accounts: {
      id: {
        initialize: (config: { callback: (r: { credential?: string }) => void }) => {
          onCredential = config.callback;
        },
        renderButton: () => {},
      },
    },
  };
}

beforeEach(() => {
  onCredential = null;
  replace.mockClear();
  refresh.mockClear();
  vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "un-client-id.apps.googleusercontent.com");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("GoogleSignIn", () => {
  it("avisa si no hay credencial configurada, en vez de mostrar un botón muerto", () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_CLIENT_ID", "");
    render(<GoogleSignIn locale="es" labels={labels} />);

    expect(screen.getByText(labels.blocked)).toBeInTheDocument();
  });

  it("canjea el id_token contra /api/session y entra a la cuenta", async () => {
    vi.stubGlobal("google", fakeGoogle());
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    render(<GoogleSignIn locale="es" labels={labels} />);
    await act(async () => onCredential!({ credential: "id-token-de-google" }));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/session");
    expect(JSON.parse(init.body)).toEqual({
      provider: "google",
      id_token: "id-token-de-google",
    });
    expect(replace).toHaveBeenCalledWith("/es/cuenta");
  });

  it("avisa si el backend rechaza la identidad", async () => {
    vi.stubGlobal("google", fakeGoogle());
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

    render(<GoogleSignIn locale="es" labels={labels} />);
    await act(async () => onCredential!({ credential: "id-token" }));

    expect(screen.getByText(labels.failed)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("no llama al servidor si Google no devolvió credencial", async () => {
    vi.stubGlobal("google", fakeGoogle());
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<GoogleSignIn locale="es" labels={labels} />);
    await act(async () => onCredential!({}));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(labels.failed)).toBeInTheDocument();
  });

  it("avisa cuando un bloqueador impide cargar el script de Google", async () => {
    render(<GoogleSignIn locale="es" labels={labels} />);

    const script = document.head.querySelector<HTMLScriptElement>(
      'script[src*="accounts.google.com"]',
    );
    expect(script).not.toBeNull();
    await act(async () => script!.onerror!(new Event("error")));

    expect(screen.getByText(labels.blocked)).toBeInTheDocument();
  });
});
