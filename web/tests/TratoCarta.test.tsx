import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TratoCarta } from "@/components/TratoCarta";
import { getDict } from "@/lib/i18n";

const ID = "58712ace-2602-4319-b8ed-785585b80955";

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const renderEn = (trato: "" | "femenino" | "masculino" | "neutro", locale: "es" | "en" | "pt" = "es") =>
  render(<TratoCarta chartId={ID} trato={trato} dict={getDict(locale)} />);

describe("TratoCarta", () => {
  it("muestra el trato actual", () => {
    renderEn("masculino");
    const dict = getDict("es");
    expect(screen.getByLabelText(dict.chart.tratoTitulo)).toHaveValue("masculino");
  });

  it("sin elegir muestra la opción vacía", () => {
    renderEn("");
    expect(screen.getByLabelText(getDict("es").chart.tratoTitulo)).toHaveValue("");
    expect(screen.getByRole("option", { name: getDict("es").newChart.tratoVacio })).toBeInTheDocument();
  });

  it("al cambiarlo llama a la ruta y muestra el nuevo", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ trato: "femenino" }) });
    renderEn("");
    const select = screen.getByLabelText(getDict("es").chart.tratoTitulo);
    fireEvent.change(select, { target: { value: "femenino" } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/charts/${ID}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ trato: "femenino" });
    await waitFor(() => expect(select).toHaveValue("femenino"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ante un error muestra el mensaje y vuelve al valor anterior", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, json: async () => ({}) });
    renderEn("neutro");
    const select = screen.getByLabelText(getDict("es").chart.tratoTitulo);
    fireEvent.change(select, { target: { value: "femenino" } });

    expect(await screen.findByRole("alert")).toHaveTextContent(getDict("es").chart.tratoError);
    expect(select).toHaveValue("neutro");
  });

  it("si la red falla también vuelve al valor anterior", async () => {
    fetchMock.mockRejectedValue(new Error("red"));
    renderEn("neutro");
    const select = screen.getByLabelText(getDict("es").chart.tratoTitulo);
    fireEvent.change(select, { target: { value: "masculino" } });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(select).toHaveValue("neutro");
  });

  it("aclara que vale desde ahora, en los tres idiomas", () => {
    for (const locale of ["es", "en", "pt"] as const) {
      const { unmount } = renderEn("", locale);
      expect(screen.getByText(getDict(locale).chart.tratoAclaracion)).toBeInTheDocument();
      unmount();
    }
    expect(getDict("es").chart.tratoAclaracion).toBe(
      "Vale para lo que se escriba o traduzca desde ahora; lo ya escrito queda como está.",
    );
    expect(getDict("en").chart.tratoAclaracion).toContain("from now on");
    expect(getDict("pt").chart.tratoAclaracion).toContain("a partir de agora");
  });

  it("en inglés, la opción vacía dice «Choose if you like»", () => {
    expect(getDict("en").newChart.tratoVacio).toBe("Choose if you like");
  });
});
