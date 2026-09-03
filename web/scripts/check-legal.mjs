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
    ["Stripe", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["no se almacena", "la IP se usa para deducir el país pero no se guarda"],
    ["Estados Unidos", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["hash irreversible", "el tombstone que queda tras borrar la cuenta"],
    ["no constituye consejo", "disclaimer de que la lectura no es asesoramiento"],
    ["vendedor registrado", "quién factura y cobra el impuesto frente al comprador"],
    ["Reembolsos", "Stripe puede reembolsar por su cuenta: la política tiene que estar escrita"],
  ],
  "en.ts": [
    ["dothecode", "identificar al responsable del tratamiento de datos"],
    ["Anthropic", "declarar el procesador que redacta las lecturas"],
    ["Stripe", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["is not stored", "la IP se usa para deducir el país pero no se guarda"],
    ["United States", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["irreversible hash", "el tombstone que queda tras borrar la cuenta"],
    ["not medical, legal, financial or professional advice", "disclaimer de asesoramiento"],
    ["merchant of record", "quién factura y cobra el impuesto frente al comprador"],
    ["Refunds", "Stripe puede reembolsar por su cuenta: la política tiene que estar escrita"],
  ],
  "pt.ts": [
    ["dothecode", "identificar al responsable del tratamiento de datos"],
    ["Anthropic", "declarar el procesador que redacta las lecturas"],
    ["Stripe", "declarar el procesador de pagos"],
    ["Sentry", "declarar la herramienta de reporte de errores"],
    ["PostHog", "declarar la analítica de producto"],
    ["não é armazenado", "la IP se usa para deducir el país pero no se guarda"],
    ["Estados Unidos", "PostHog y Sentry procesan fuera de la UE: transferencia internacional"],
    ["hash irreversível", "el tombstone que queda tras borrar la cuenta"],
    ["não constitui aconselhamento", "disclaimer de asesoramiento"],
    ["vendedora registrada", "quién factura y cobra el impuesto frente al comprador"],
    ["Reembolsos", "a Stripe pode reembolsar por conta própria: a política tem que estar escrita"],
  ],
};

/** Lo que NO puede volver al texto, con el motivo por el que se fue.
 *
 * El modelo de créditos murió el 01-09-2026 y la app no se está construyendo,
 * pero los legales siguieron prometiendo créditos comprados en Google Play y
 * reembolsos gestionados por "la tienda" hasta el 03-09. Nadie lo vio porque el
 * único chequeo que leía estos archivos EXIGÍA justamente esas menciones.
 */
const FORBIDDEN = [
  [/RevenueCat/i, "el cobro ya no pasa por RevenueCat sino por Stripe"],
  [/Google Play/i, "no hay app: no se compra en ninguna tienda"],
  [/App Store/i, "no hay app: no se compra en ninguna tienda"],
  [/cr[eé]ditos?\b/i, "no hay créditos desde el 01-09-2026: hay derechos sobre productos"],
  [/\bcredits\b/i, "no hay créditos desde el 01-09-2026: hay derechos sobre productos"],
  [/\b1 credit\b/i, "no hay créditos desde el 01-09-2026: hay derechos sobre productos"],
];

let failures = 0;

for (const [file, checks] of Object.entries(REQUIRED)) {
  const source = readFileSync(join(contentDir, file), "utf8");
  for (const [needle, why] of checks) {
    if (!source.includes(needle)) {
      console.error(`✗ ${file}: falta "${needle}" — ${why}`);
      failures += 1;
    }
  }
  for (const [pattern, why] of FORBIDDEN) {
    const hit = source.match(pattern);
    if (hit) {
      console.error(`✗ ${file}: dice "${hit[0]}" y no debería — ${why}`);
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
