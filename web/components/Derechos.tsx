import type { Dict } from "@/lib/i18n";
import { cantidad, type Derecho } from "@/lib/derechos";

/**
 * Qué puede hacer la cuenta ahora mismo — no cuánta moneda tiene.
 *
 * El backend ya no habla de créditos: habla de derechos sobre productos
 * concretos (Task 16). Esta pantalla es la que dejaba de reflejarlo: mostraba
 * "☉ 3 · ☾ 0" como si fueran dos saldos, y nadie sabía qué significaba un
 * "crédito". Acá cada línea dice qué se puede leer, en el idioma de la
 * persona ("2 lecturas breves"), y sin derechos activos no se muestra un
 * "0" — se ofrece lo único que hoy se puede comprar.
 */
const PRODUCTOS = [
  {
    codigo: "lectura_breve",
    glifo: "☉",
    texto: (dict: Dict, n: number) =>
      n === 1 ? dict.auth.derechosBreveUno : dict.auth.derechosBreve.replace("{n}", String(n)),
  },
  {
    codigo: "informe_natal",
    glifo: "☾",
    texto: (dict: Dict, n: number) =>
      n === 1
        ? dict.auth.derechosInformeUno
        : dict.auth.derechosInforme.replace("{n}", String(n)),
  },
] as const;

export function Derechos({ derechos, dict }: { derechos: Derecho[]; dict: Dict }) {
  // `cantidad` ya trae 0 para lo que no está en la lista o ya se agotó
  // (`cantidad_restante: 0`): filtrar por > 0 es lo que evita mostrar "0
  // lecturas breves" en vez de simplemente no listar esa línea.
  const lineas = PRODUCTOS.map((producto) => ({
    ...producto,
    n: cantidad(derechos, producto.codigo),
  })).filter((linea) => linea.n > 0);

  if (lineas.length === 0) {
    return (
      <div className="derechos derechosVacio">
        <p className="derechosOferta">{dict.auth.sinDerechos}</p>
        <div className="buyBlock">
          <button type="button" className="btn btnGhost" disabled>
            {dict.auth.comprarInforme}
          </button>
          <p className="buyNote">{dict.auth.comprarNota}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="derechos">
      {lineas.map((linea) => (
        <p key={linea.codigo} className="balance">
          <span className="balanceGlyph" aria-hidden="true">
            {linea.glifo}
          </span>
          <span className="derechoTexto">{linea.texto(dict, linea.n)}</span>
        </p>
      ))}
    </div>
  );
}
