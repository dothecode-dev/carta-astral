import Link from "next/link";

import { formatearPrecio } from "@/lib/catalogo";
import { INTL_LOCALE, type Dict, type Locale } from "@/lib/i18n";

/**
 * Lo que la cuenta compró: qué, cuánto se pagó (y con qué cupón), cuándo, y
 * si volvió la plata.
 *
 * Muestra también lo que todavía no acreditó. Si viene con `url`, la sesión
 * de Stripe sigue abierta: es un pago sin terminar y se ofrece retomarlo ahí
 * mismo. Sin `url`, es un pago cuyo webhook aún no llegó —hay medios de pago
 * que no son instantáneos— y esconderlo haría pensar que se perdió la plata.
 * Lo que no se muestra es un checkout vencido: el backend lo deja de listar
 * cuando Stripe avisa que la sesión venció.
 */
export type Compra = {
  codigo_producto: string;
  acreditada: boolean;
  created_at: string;
  monto_centavos: number;
  cupon: string | null;
  reembolsado_centavos: number;
  /** La sesión de Stripe, sólo mientras se puede retomar el pago. */
  url: string | null;
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
  const precio = (centavos: number) => formatearPrecio(centavos, "usd", INTL_LOCALE[locale]);

  return (
    <ul className="compras">
      {compras.map((compra) => {
        const reembolsada = compra.reembolsado_centavos > 0 && compra.reembolsado_centavos >= compra.monto_centavos;
        const parcial = compra.reembolsado_centavos > 0 && !reembolsada;
        return (
          <li
            key={`${compra.codigo_producto}-${compra.created_at}`}
            className={`compra${reembolsada ? " compraReembolsada" : ""}`}
          >
            <span className="compraNombre">
              {dict.precios.nombre[compra.codigo_producto] ?? compra.codigo_producto}
            </span>
            {/* Un regalo del 100 % no vale «US$ 0»: vale gratis, y dice con qué. */}
            <span className="compraMonto">
              {compra.monto_centavos === 0 ? dict.precios.gratisPrecio : precio(compra.monto_centavos)}
            </span>
            {compra.cupon && (
              <span className="compraCupon">
                {dict.auth.compraCupon.replace("{codigo}", compra.cupon)}
              </span>
            )}
            <span className="compraFecha">{fecha.format(new Date(compra.created_at))}</span>
            {!compra.acreditada && compra.url && (
              <>
                <span className="compraPendiente">{dict.auth.compraSinTerminar}</span>
                <a className="compraRetomar" href={compra.url}>{dict.auth.compraRetomar}</a>
              </>
            )}
            {!compra.acreditada && !compra.url && (
              <span className="compraPendiente">{dict.auth.compraPendiente}</span>
            )}
            {reembolsada && <span className="compraEstado">{dict.auth.compraReembolsada}</span>}
            {parcial && (
              <span className="compraEstado">
                {dict.auth.compraReembolsoParcial.replace("{monto}", precio(compra.reembolsado_centavos))}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
