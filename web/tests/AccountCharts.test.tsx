import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountCharts, type ChartSummary } from "@/components/AccountCharts";
import { ChartTables } from "@/components/ChartTables";
import type { ApiChart } from "@/lib/chart";
import { getDict } from "@/lib/i18n";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const dict = getDict("es");

function carta(over: Partial<ChartSummary> = {}): ChartSummary {
  return {
    id: "abc",
    interpretation_langs: [],
    birth: { name: "Ceci", date: "1989-07-14", time: "23:45", place_label: "Rosario, AR" },
    data: { placements: [{ name: "Sun", abs_pos: 112.487 }] },
    ...over,
  };
}

describe("AccountCharts", () => {
  it("invita a calcular la primera cuando no hay ninguna", () => {
    render(<AccountCharts charts={[]} locale="es" dict={dict} />);

    expect(screen.getByText(dict.auth.chartsEmpty)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: dict.auth.chartsEmptyCta })).toHaveAttribute(
      "href",
      "/es/nueva",
    );
  });

  it("muestra fecha, hora, lugar y el signo solar", () => {
    render(<AccountCharts charts={[carta()]} locale="es" dict={dict} />);
    const fila = screen.getByRole("link");

    expect(fila).toHaveAttribute("href", "/es/carta/abc");
    expect(within(fila).getByText("Ceci")).toBeInTheDocument();
    expect(within(fila).getByText("Rosario, AR")).toBeInTheDocument();
    expect(within(fila).getByText(/23:45/)).toBeInTheDocument();
    // Sol en Cáncer: es el glifo que muestra la app.
    expect(within(fila).getByText("♋")).toBeInTheDocument();
  });

  it("no corre la fecha de nacimiento un día por la zona horaria", () => {
    // Una fecha de nacimiento no es un instante: interpretarla en horario local
    // adelanta o atrasa el día según dónde esté quien mira.
    render(
      <AccountCharts
        charts={[carta({ birth: { name: null, date: "2007-05-17", time: null, place_label: "x" } })]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(/17 may 2007/)).toBeInTheDocument();
  });

  it("nombra las cartas sin nombre y omite la hora que no se sabe", () => {
    render(
      <AccountCharts
        charts={[carta({ birth: { name: null, date: "1989-07-14", time: null, place_label: "x" } })]}
        locale="es"
        dict={dict}
      />,
    );

    expect(screen.getByText(dict.auth.unnamedChart)).toBeInTheDocument();
    expect(screen.queryByText(/·\s*\d{2}:\d{2}/)).not.toBeInTheDocument();
  });

  it("dice en qué idiomas ya está leída", () => {
    render(
      <AccountCharts charts={[carta({ interpretation_langs: ["es", "en"] })]} locale="es" dict={dict} />,
    );

    expect(screen.getByText(/ES · EN/)).toBeInTheDocument();
  });
});

function chartCon(data: Partial<ApiChart["data"]>): ApiChart {
  return {
    id: "x",
    interpretation_langs: [],
    birth: { name: null, date: "1989-07-14", time: "23:45", time_known: true, place_label: "x" },
    data: {
      placements: [],
      houses: null,
      angles: null,
      aspects: [],
      flags: {
        moon_approximate: false,
        precision_degraded: false,
        bodies_missing: false,
        house_system_fallback: false,
      },
      ...data,
    },
  };
}

describe("ChartTables", () => {
  it("no muestra tablas vacías", () => {
    const { container } = render(<ChartTables chart={chartCon({})} dict={dict} />);
    expect(container.querySelectorAll("details")).toHaveLength(0);
  });

  it("numera las casas en romanos y las trae cerradas", () => {
    render(
      <ChartTables
        chart={chartCon({
          houses: [
            { name: "First_House", abs_pos: 15.5 },
            { name: "Second_House", abs_pos: 45 },
          ],
        })}
        dict={dict}
      />,
    );

    const bloque = screen.getByText(dict.chart.houses).closest("details")!;
    expect(bloque.open).toBe(false);
    expect(within(bloque).getByText("I")).toBeInTheDocument();
    expect(within(bloque).getByText(/15°30′ ♈/)).toBeInTheDocument();
    expect(within(bloque).getByText(/15°00′ ♉/)).toBeInTheDocument();
  });

});
