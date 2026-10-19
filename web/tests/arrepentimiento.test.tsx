import { act, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Botón de arrepentimiento (Res. SCI 424/2020; mini-spec del 19-10-2026). El
// formulario registra el pedido y muestra el código: no reembolsa nada.

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
  headers: async () => new Headers({ "x-forwarded-for": "200.1.2.3" }),
}));

import { POST } from "@/app/api/arrepentimiento/route";
import { ArrepentimientoForm } from "@/components/ArrepentimientoForm";
import { Footer } from "@/components/Footer";
import { LOCALES, getDict } from "@/lib/i18n";

const dict = getDict("es");
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const req = (body: unknown) =>
  new Request("http://x/api/arrepentimiento", { method: "POST", body: JSON.stringify(body) });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("POST /api/arrepentimiento", () => {
  it("le pega al backend sin sesión y sólo con los campos del formulario", async () => {
    fetchMock.mockResolvedValue(json({ codigo: "ARR-ABCD2345" }, 201));

    const res = await POST(req({ email: "a@b.com", numero_compra: "x1", locale: "es", otro: "no" }));

    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ codigo: "ARR-ABCD2345" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/arrepentimiento/");
    expect(new Headers(init.headers).get("Authorization")).toBeNull();
    expect(JSON.parse(init.body)).toEqual({ email: "a@b.com", numero_compra: "x1", locale: "es" });
  });

  it("un mail inválido llega como 400 con su motivo", async () => {
    fetchMock.mockResolvedValue(json({ error: "x", motivo: "email_invalido" }, 400));

    const res = await POST(req({ email: "nada" }));

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ motivo: "email_invalido" });
  });

  it.each([[429, 429], [500, 502]])("backend %s → %s", async (backend, esperado) => {
    fetchMock.mockResolvedValue(json({}, backend));

    expect((await POST(req({ email: "a@b.com" }))).status).toBe(esperado);
  });
});

describe("el formulario", () => {
  const t = dict.arrepentimiento;

  it("con el mail registra el pedido y muestra el código", async () => {
    fetchMock.mockResolvedValue(json({ codigo: "ARR-ABCD2345" }, 201));
    render(<ArrepentimientoForm locale="es" dict={dict} />);

    fireEvent.change(screen.getByLabelText(t.mailLabel), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(t.numeroLabel), { target: { value: "x1" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.enviar }));
    });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: "a@b.com", numero_compra: "x1", locale: "es" });
    expect(screen.getByText("ARR-ABCD2345")).toBeTruthy();
    expect(screen.queryByRole("button", { name: t.enviar })).toBeNull();
  });

  it("un mail inválido lo dice y deja corregir", async () => {
    fetchMock.mockResolvedValue(json({ motivo: "email_invalido" }, 400));
    render(<ArrepentimientoForm locale="es" dict={dict} />);

    fireEvent.change(screen.getByLabelText(t.mailLabel), { target: { value: "a@b" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.enviar }));
    });

    expect(screen.getByRole("alert").textContent).toBe(t.mailInvalido);
    expect((screen.getByRole("button", { name: t.enviar }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("cualquier otra falla lo dice con el mail de contacto", async () => {
    fetchMock.mockResolvedValue(json({}, 502));
    render(<ArrepentimientoForm locale="es" dict={dict} />);

    fireEvent.change(screen.getByLabelText(t.mailLabel), { target: { value: "a@b.com" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: t.enviar }));
    });

    expect(screen.getByRole("alert").textContent).toBe(t.fallo);
  });
});

describe("el enlace (RA1)", () => {
  it.each(LOCALES)("está en el pie de todas las páginas (%s)", (locale) => {
    const html = renderToStaticMarkup(<Footer locale={locale} dict={getDict(locale)} />);

    expect(html).toContain(`href="/${locale}/arrepentimiento"`);
    expect(html).toContain(getDict(locale).foot.arrepentimiento);
  });
});
