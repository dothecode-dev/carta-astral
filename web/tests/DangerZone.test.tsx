import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DangerZone } from "@/components/DangerZone";
import { getDict } from "@/lib/i18n";

// Borrar es irreversible y no hay forma de deshacerlo desde acá: lo que se
// prueba es que nada se borre de un solo click y que un borrado que falló no
// se muestre como cumplido.

const refresh = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, replace }) }));

const dict = getDict("es");
const t = dict.auth;

const ok = { ok: true, status: 200 };
const falla = { ok: false, status: 502 };

function abrir(titulo: string) {
  fireEvent.click(screen.getAllByRole("button", { name: titulo })[0]);
}

async function confirmar(texto: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: texto }));
  });
}

beforeEach(() => {
  refresh.mockClear();
  replace.mockClear();
  render(<DangerZone locale="es" dict={dict} />);
});

afterEach(() => vi.unstubAllGlobals());

describe("DangerZone", () => {
  it("no borra nada con un solo click", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    abrir(t.deleteChartsTitle);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(t.confirmHint)).toBeInTheDocument();
  });

  it("se puede cancelar antes de confirmar", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    abrir(t.deleteAccountTitle);
    fireEvent.click(screen.getByRole("button", { name: t.cancel }));

    expect(screen.queryByText(t.confirmHint)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("borra las cartas y se queda en la cuenta", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok);
    vi.stubGlobal("fetch", fetchMock);

    abrir(t.deleteChartsTitle);
    await confirmar(t.deleteChartsConfirm);

    expect(fetchMock).toHaveBeenCalledWith("/api/charts", { method: "DELETE" });
    expect(refresh).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();
  });

  it("borra la cuenta y saca a la persona de la sesión", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok);
    vi.stubGlobal("fetch", fetchMock);

    abrir(t.deleteAccountTitle);
    await confirmar(t.deleteAccountConfirm);

    expect(fetchMock).toHaveBeenCalledWith("/api/account", { method: "DELETE" });
    expect(replace).toHaveBeenCalledWith("/es");
  });

  it("un borrado que falló no navega ni refresca", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(falla));

    abrir(t.deleteAccountTitle);
    await confirmar(t.deleteAccountConfirm);

    expect(replace).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    // Y la confirmación se cierra: la próxima vez vuelve a pedirla.
    expect(screen.queryByText(t.confirmHint)).not.toBeInTheDocument();
  });

  it("no confunde las dos acciones: confirmar una no abre la otra", () => {
    vi.stubGlobal("fetch", vi.fn());

    abrir(t.deleteChartsTitle);

    expect(screen.queryByRole("button", { name: t.deleteAccountConfirm })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.deleteChartsConfirm })).toBeInTheDocument();
  });
});
