import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SolarSystem } from "@/components/SolarSystem";

describe("SolarSystem", () => {
  it("no mezcla el ángulo de partida con la animación", () => {
    // Cuando el ángulo inicial vivía en el mismo elemento que la animación, el
    // keyframe —que sólo declara el `to`— lo tomaba como punto de partida: un
    // planeta que arranca en 162° recorría 198 grados y saltaba de golpe al
    // empezar la vuelta siguiente. Ese salto es lo que se veía como un corte.
    const { container } = render(<SolarSystem />);

    for (const orbita of container.querySelectorAll(".solarOrbit")) {
      expect(orbita.getAttribute("style") ?? "").not.toContain("rotate");
      expect(orbita.getAttribute("transform")).toBeNull();
    }
  });

  it("cada órbita gira a su propio período", () => {
    const { container } = render(<SolarSystem speed={2} />);
    const duraciones = [...container.querySelectorAll(".solarOrbit")].map(
      (o) => (o as HTMLElement).style.animationDuration,
    );
    // 20000ms y 12000ms a velocidad 2.
    expect(duraciones).toEqual(["10000ms", "6000ms"]);
  });

  it("el ángulo de partida se aplica en un grupo aparte", () => {
    const { container } = render(<SolarSystem />);
    const envoltorios = [...container.querySelectorAll("g[transform]")].map((g) =>
      g.getAttribute("transform"),
    );
    expect(envoltorios).toEqual(["rotate(162 100 100)", "rotate(-47 100 100)"]);
  });
});
