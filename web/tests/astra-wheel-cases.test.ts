import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

import { buildWheel } from "astra-wheel";
import { describe, expect, it } from "vitest";

// Los casos compartidos que tambien corren la app (jest) y el backend (pytest).
// Si esto falla, la web se separo de las otras dos superficies.
const DIR = join(dirname(createRequire(import.meta.url).resolve("astra-wheel")), "..", "cases");
const TOL = 0.1;

function compare(actual: unknown, expected: unknown, path: string): void {
  if (typeof expected === "number") {
    expect(typeof actual, `${path}: tipo`).toBe("number");
    expect(Math.abs((actual as number) - expected), path).toBeLessThanOrEqual(TOL);
    return;
  }
  if (Array.isArray(expected)) {
    expect((actual as unknown[]).length, `${path}: largo`).toBe(expected.length);
    expected.forEach((e, i) => compare((actual as unknown[])[i], e, `${path}[${i}]`));
    return;
  }
  if (expected && typeof expected === "object") {
    for (const [k, v] of Object.entries(expected)) {
      compare((actual as Record<string, unknown>)[k], v, `${path}.${k}`);
    }
    return;
  }
  expect(actual, path).toBe(expected);
}

const casos = readdirSync(DIR).filter((f) => f.endsWith(".json"));

describe("la web dibuja lo mismo que el paquete", () => {
  it("los casos compartidos estan instalados", () => {
    expect(casos.length).toBeGreaterThanOrEqual(5);
  });

  for (const archivo of casos) {
    const caso = JSON.parse(readFileSync(join(DIR, archivo), "utf8"));
    it(caso.name, () => {
      compare(buildWheel(caso.input, caso.options), caso.expected, caso.name);
    });
  }
});
