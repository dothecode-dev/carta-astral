import Link from "next/link";

import { INTL_LOCALE, type Dict, type Locale } from "@/lib/i18n";

/**
 * Lo que la cuenta compró.
 *
 * Muestra también lo que todavía no acreditó: si alguien pagó y el webhook aún
 * no llegó —hay medios de pago que no son instantáneos—, esconder la compra
 * haría pensar que se perdió la plata.
 */
export type Compra = {
  codigo_producto: string;
  acreditada: boolean;
  created_at: string;
};

export function Compras({
  compras,
  locale,
  dict,
}: {
  compras: Compra[];
  locale: Locale;
  dict: Dict;
}) {
  if (compras.length === 0) {
    return (
      <div className="comprasVacio">
        <p className="fieldNote">{dict.auth.comprasEmpty}</p>
        <Link className="btn btnGhost" href={`/${locale}/precios`}>
          {dict.auth.verPrecios}
        </Link>
      </div>
    );
  }

  const fecha = new Intl.DateTimeFormat(INTL_LOCALE[locale], { dateStyle: "medium" });

  return (
    <ul className="compras">
      {compras.map((compra) => (
        <li key={`${compra.codigo_producto}-${compra.created_at}`} className="compra">
          <span className="compraNombre">
            {dict.precios.nombre[compra.codigo_producto] ?? compra.codigo_producto}
          </span>
          <span className="compraFecha">{fecha.format(new Date(compra.created_at))}</span>
          {!compra.acreditada && (
            <span className="compraPendiente">{dict.auth.compraPendiente}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
