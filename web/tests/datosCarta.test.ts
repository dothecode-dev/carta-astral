import { describe, expect, it } from "vitest";

import type { Place } from "@/app/api/geocode/route";
import { armarDatosCarta, errorDeFecha } from "@/lib/datosCarta";

const ROSARIO: Place = {
  place_query: "Rosario, Santa Fe, AR",
  name: "Rosario",
  lat: -32.94682,
  lng: -60.63932,
  tz_name: "America/Argentina/Cordoba",
  country_code: "AR",
  admin1: "Santa Fe",
  population: 1193605,
};

describe("armarDatosCarta", () => {
  it("con hora: la manda y marca time_known", () => {
    expect(
      armarDatosCarta({ name: "Ceci", date: "1976-05-31", time: "19:30", timeUnknown: false, place: ROSARIO }),
    ).toEqual({
      name: "Ceci",
      date: "1976-05-31",
      time: "19:30",
      time_known: true,
      lat: -32.94682,
      lng: -60.63932,
      place_label: "Rosario, Santa Fe, AR",
    });
  });

  it("«no sé la hora» gana aunque haya una hora escrita", () => {
    const d = armarDatosCarta({ name: null, date: "1976-05-31", time: "19:30", timeUnknown: true, place: ROSARIO });
    expect(d.time).toBeNull();
    expect(d.time_known).toBe(false);
  });

  it("sin hora escrita tampoco hay hora conocida", () => {
    const d = armarDatosCarta({ name: null, date: "1976-05-31", time: "", timeUnknown: false, place: ROSARIO });
    expect(d.time).toBeNull();
    expect(d.time_known).toBe(false);
  });

  it("el nombre pasa tal cual: null queda null", () => {
    const d = armarDatosCarta({ name: null, date: "1976-05-31", time: "", timeUnknown: true, place: ROSARIO });
    expect(d.name).toBeNull();
  });
});

describe("errorDeFecha", () => {
  it("vacía es needDate", () => {
    expect(errorDeFecha("")).toBe("needDate");
  });

  it("antes de 1800 es badDate", () => {
    expect(errorDeFecha("1799-12-31")).toBe("badDate");
  });

  it("en el futuro es badDate", () => {
    const manana = new Date(Date.now() + 2 * 24 * 3600 * 1000).toISOString().slice(0, 10);
    expect(errorDeFecha(manana)).toBe("badDate");
  });

  it("una fecha normal no tiene error", () => {
    expect(errorDeFecha("1976-05-31")).toBeNull();
    expect(errorDeFecha("1800-01-01")).toBeNull();
  });
});
