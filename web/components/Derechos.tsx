import Link from "next/link";

import type { Dict, Locale } from "@/lib/i18n";
import { cantidad, type Derecho } from "@/lib/derechos";

/**
 * Qué puede hacer la cuenta ahora mismo — no cuánta moneda tiene.
 *
 * El backend ya no habla de créditos: habla de derechos sobre productos
 * concretos (Task 16). Esta pantalla es la que dejaba de reflejarlo: mostraba
 * "☉ 3 · ☾ 0" como si fueran dos saldos, y nadie sabía qué significaba un
 * "crédito".
 *
 * Después pasó a decir "3 lecturas breves", que sigue siendo un inventario: un
 * número. Ahora cada unidad disponible es UNA LÍNEA, y cada línea es el enlace
 * a usarla. Lo que la persona necesita saber no es cuántas tiene sino qué
 * puede hacer con ellas — y eso era exactamente lo que no encontraba: de tres
 * usuarios reales, ninguno llegó a generar una lectura (04-09-2026).
 */
const PRODUCTOS = [
  { codigo: "lectura_breve", glifo: "☉", nombre: (dict: Dict) => dict.auth.usoBreve },
  { codigo: "informe_natal", glifo: "☾", nombre: (dict: Dict) => dict.auth.usoInforme },
] as const;

/**
 * Cuántas líneas individuales se abren por producto.
 *
 * Con un pack de cinco son cinco renglones, que se leen bien. Con tres packs
 * serían quince idénticos: ahí la lista deja de informar y se vuelve ruido, y
 * conviene volver al recuento agrupado.
 */
const MAX_LINEAS = 5;

export function Derechos({
  derechos,
  dict,
  locale,
  hayCartas,
}: {
  derechos: Derecho[];
  dict: Dict;
  locale: Locale;
  /** Decide a dónde va cada línea: a elegir entre las cartas que ya existen, o
   *  a calcular la primera. Sin esto el bloque enumeraba lo que la cuenta tiene
   *  y no decía en ningún lado dónde se usa. */
  hayCartas: boolean;
}) {
  // El destino es el mismo para todas las líneas: el derecho se gasta sobre una
  // carta, así que primero hay que elegir una (o crearla).
  const destino = hayCartas ? "#tus-cartas" : `/${locale}/nueva`;
  const accion = hayCartas ? dict.auth.listoUsar : dict.auth.listoUsarSinCartas;

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
        {disponibles.flatMap((linea) =>
          linea.n <= MAX_LINEAS
            ? // Una línea por unidad: cada una es algo que se puede hacer.
              Array.from({ length: linea.n }, (_, i) => (
                <li key={`${linea.codigo}-${i}`}>
                  <Link className="uso" href={destino}>
                    <span className="usoGlifo" aria-hidden="true">
                      {linea.glifo}
                    </span>
                    <span className="usoNombre">{linea.nombre(dict)}</span>
                    {/* El destino, a la derecha. Aparece al apuntar o al llegar
                        con el teclado: es lo que convierte tres renglones
                        iguales en tres cosas para hacer, sin repetir la misma
                        frase tres veces en pantalla. */}
                    <span className="usoAccion" aria-hidden="true">
                      {accion}
                    </span>
                  </Link>
                </li>
              ))
            : // Demasiadas para listar de a una: vuelve el recuento.
              [
                <li key={linea.codigo}>
                  <Link className="uso" href={destino}>
                    <span className="usoGlifo" aria-hidden="true">
                      {linea.glifo}
                    </span>
                    <span className="usoNombre">
                      {linea.codigo === "lectura_breve"
                        ? dict.auth.derechosBreve.replace("{n}", String(linea.n))
                        : dict.auth.derechosInforme.replace("{n}", String(linea.n))}
                    </span>
                    <span className="usoAccion" aria-hidden="true">
                      {accion}
                    </span>
                  </Link>
                </li>,
              ],
        )}
      </ul>

      {/* Debajo del listado y en gris: comprar más es lo que se hace cuando ya
          no queda nada de lo de arriba, no la acción principal de este bloque. */}
      <Link className="derechosMas" href={`/${locale}/precios`}>
        {dict.auth.verPrecios}
      </Link>
    </div>
  );
}
