// Reemplaza la garantía que daba backend/tests/api/test_legal_pages.py cuando
// los legales vivían en Django: que el texto no pierda las menciones que la
// política promete y que las tiendas exigen.
//
// Lee los archivos como texto en vez de importarlos: no necesita compilar TS ni
// depender de flags de Node, y lo que se audita es exactamente lo versionado.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const contentDir = join(here, "..", "content", "legal");

/** Cada mención existe porque algo la exige; el motivo va al lado. */
const REQUIRED = {
  "es.ts": [
    ["dothecode", "identificar al responsable del tratamiento de datos"],
    ["Anthropic", "declarar el procesador que redacta las lecturas"],
    ["RevenueCat", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["no se almacena", "la IP se usa para deducir el país pero no se guarda"],
    ["Estados Unidos", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["hash irreversible", "el tombstone que queda tras borrar la cuenta"],
    ["no constituye consejo", "disclaimer de que la lectura no es asesoramiento"],
    ["1 crédito", "qué consume una interpretación"],
  ],
  "en.ts": [
    ["dothecode", "identificar al responsable del tratamiento de datos"],
    ["Anthropic", "declarar el procesador que redacta las lecturas"],
    ["RevenueCat", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["is not stored", "la IP se usa para deducir el país pero no se guarda"],
    ["United States", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["irreversible hash", "el tombstone que queda tras borrar la cuenta"],
    ["not medical, legal, financial or professional advice", "disclaimer de asesoramiento"],
    ["1 credit", "qué consume una interpretación"],
  ],
  "pt.ts": [
    ["dothecode", "identificar al responsable del tratamiento de datos"],
    ["Anthropic", "declarar el procesador que redacta las lecturas"],
    ["RevenueCat", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["não é armazenado", "la IP se usa para deducir el país pero no se guarda"],
    ["Estados Unidos", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["hash irreversível", "el tombstone que queda tras borrar la cuenta"],
    ["não constitui aconselhamento", "disclaimer de asesoramiento"],
    ["1 crédito", "qué consume una interpretación"],
  ],
};

let failures = 0;

for (const [file, checks] of Object.entries(REQUIRED)) {
  const source = readFileSync(join(contentDir, file), "utf8");
  for (const [needle, why] of checks) {
    if (!source.includes(needle)) {
      console.error(`✗ ${file}: falta "${needle}" — ${why}`);
      failures += 1;
    }
  }
}

// Los tres idiomas tienen que declarar la misma fecha de revisión.
const updated = readFileSync(join(contentDir, "types.ts"), "utf8").match(
  /LEGAL_UPDATED = "(\d{4}-\d{2}-\d{2})"/,
);
if (!updated) {
  console.error("✗ types.ts: LEGAL_UPDATED no tiene una fecha con formato AAAA-MM-DD");
  failures += 1;
}

if (failures > 0) {
  console.error(`\n${failures} problema(s) en los documentos legales.`);
  process.exit(1);
}

console.log(
  `✓ Documentos legales completos en es/en/pt (última revisión: ${updated ? updated[1] : "?"})`,
);
