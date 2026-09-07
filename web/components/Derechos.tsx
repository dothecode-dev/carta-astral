import Link from "next/link";

import type { Dict, Locale } from "@/lib/i18n";
import { cantidad, type Derecho } from "@/lib/derechos";

/**
 * Qué puede hacer la cuenta ahora mismo, y a qué se le asigna.
 *
 * El backend no habla de créditos: habla de derechos sobre productos
 * concretos. Acá cada producto disponible es una línea con cuántas quedan y
 * dos salidas: usarlo en una carta nueva —calcularla y que arranque solo— o en
 * una de las que ya existen. Antes había una fila por unidad que sólo hacía
 * scroll a «Tus cartas», y el caso real no tenía camino: «tengo un informe
 * pago y quiero dárselo a Carlos, que todavía no tiene carta, sin gastar una
 * lectura gratuita» (06-09-2026).
 *
 * Una lectura es la interpretación de una carta: sin fecha, hora y lugar de
 * nacimiento no hay nada que leer. Por eso las dos salidas terminan en una
 * carta, y por eso, sin ninguna, se dice que calcularla es gratis.
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
      n === 1 ? dict.auth.derechosInformeUno : dict.auth.derechosInforme.replace("{n}", String(n)),
  },
] as const;

export function Derechos({
  derechos,
  dict,
  locale,
  hayCartas,
}: {
  derechos: Derecho[];
  dict: Dict;
  locale: Locale;
  /** Con cartas se ofrece también usarlo en una de ellas; sin ninguna, sólo
   *  la nueva, y se explica por qué hace falta una. */
  hayCartas: boolean;
}) {
  // `cantidad` ya trae 0 para lo que no está en la lista o ya se agotó, así que
  // filtrar por > 0 es lo que evita mostrar "0 lecturas breves" en vez de
  // simplemente no listar esa línea.
  const disponibles = PRODUCTOS.map((producto) => ({
    ...producto,
    n: cantidad(derechos, producto.codigo),
  })).filter((linea) => linea.n > 0);

  if (disponibles.length === 0) {
    return (
      <div className="derechos derechosVacio">
        <p className="derechosOferta">{dict.auth.sinDerechos}</p>
        <div className="buyBlock">
          <Link className="btn btnPrimary" href={`/${locale}/precios`}>
            {dict.auth.comprarInforme}
          </Link>
          <p className="buyNote">{dict.auth.comprarNota}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="derechos">
      <ul className="usos">
        {disponibles.map((linea) => (
          <li key={linea.codigo} className="uso">
            <span className="usoGlifo" aria-hidden="true">
              {linea.glifo}
            </span>
            <span className="usoNombre">{linea.texto(dict, linea.n)}</span>
            <span className="usoAcciones">
              {/* Primero la nueva: es el camino que no existía, y el que no
                  depende de nada. */}
              <Link className="usoAccion" href={`/${locale}/nueva?usar=${linea.codigo}`}>
                {dict.auth.usarEnNueva}
              </Link>
              {hayCartas && (
                <Link className="usoAccion" href="#tus-cartas">
                  {dict.auth.usarEnMisCartas}
                </Link>
              )}
            </span>
          </li>
        ))}
      </ul>

      <p className="derechosNota">{dict.auth.listoNota}</p>
      {!hayCartas && <p className="derechosNota">{dict.auth.listoSinCartasNota}</p>}

      {/* Debajo del listado y en gris: comprar más es lo que se hace cuando ya
          no queda nada de lo de arriba, no la acción principal de este bloque. */}
      <Link className="derechosMas" href={`/${locale}/precios`}>
        {dict.auth.verPrecios}
      </Link>
    </div>
  );
}
