"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { normalizarCupon } from "@/lib/cupon";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

/**
 * El cupón en /precios, en el estado que corresponda:
 *
 * - sin cupón, una línea discreta («Tengo un cupón») que abre el campo: la
 *   mayoría llega sin uno, y un formulario abierto es ruido en la pantalla
 *   donde se decide comprar;
 * - con un cupón válido, una etiqueta pegada a la grilla que dice cuál y
 *   cuánto, con «Quitar»: los precios tachados de abajo ya cuentan el resto;
 * - con uno rechazado, el campo abierto con el código y el motivo.
 *
 * No calcula nada: manda el código a la URL (`?cupon=`) y la página vuelve a
 * pintarse con los precios que devuelve el backend. Es el mismo camino que el
 * link de Instagram: una sola forma de aplicar un cupón, una sola fuente del
 * número.
 */
export function CuponInput({
  locale,
  dict,
  inicial,
  estado,
  porcentaje,
}: {
  locale: Locale;
  dict: Dict;
  /** El código que venía en la URL, para dejarlo escrito. */
  inicial: string | null;
  /** `valido`, un motivo de rechazo, o null si no había cupón. */
  estado: string | null;
  porcentaje?: number;
}) {
  const router = useRouter();
  const id = useId();
  const [codigo, setCodigo] = useState(inicial ?? "");
  // Abierto si vino un código que no sirvió: hay algo que corregir.
  const [abierto, setAbierto] = useState(Boolean(inicial) && estado !== "valido");
  const [invalido, setInvalido] = useState(false);

  // Se mide cuando la página ya sabe si sirvió, no al escribirlo: es la única
  // forma de contar «quiso usar un cupón y no pudo», que es lo que importa.
  useEffect(() => {
    if (inicial && estado) track("cupon_aplicado", { codigo: inicial, resultado: estado });
  }, [inicial, estado]);

  if (inicial && estado === "valido") {
    return (
      <p className="cuponAplicado" role="status">
        <span className="cuponChip">
          {dict.precios.cuponAplicado
            .replace("{codigo}", inicial)
            .replace("{porcentaje}", String(porcentaje ?? ""))}
        </span>
        <Link className="cuponQuitar" href={`/${locale}/precios`}>
          {dict.precios.cuponQuitar}
        </Link>
      </p>
    );
  }

  if (!abierto) {
    return (
      <p className="cuponLinea">
        <button type="button" className="cuponAbrir" onClick={() => setAbierto(true)}>
          {dict.precios.cuponTengo}
        </button>
      </p>
    );
  }

  const aplicar = (e: React.FormEvent) => {
    e.preventDefault();
    const normalizado = normalizarCupon(codigo);
    if (!normalizado) {
      setInvalido(true);
      return;
    }
    setInvalido(false);
    router.push(`/${locale}/precios?cupon=${encodeURIComponent(normalizado)}`);
  };

  const motivo = invalido
    ? dict.precios.cuponMotivo.invalido
    : estado
      ? (dict.precios.cuponMotivo[estado] ?? dict.precios.cuponMotivo.invalido)
      : null;

  return (
    <form className="cuponForm" onSubmit={aplicar}>
      <label className="cuponLabel" htmlFor={id}>
        {dict.precios.cuponLabel}
      </label>
      <input
        id={id}
        className="cuponInput"
        name="cupon"
        value={codigo}
        onChange={(e) => setCodigo(e.target.value)}
        autoCapitalize="characters"
        autoComplete="off"
        spellCheck={false}
        maxLength={40}
        autoFocus={!inicial}
      />
      <button type="submit" className="btn btnGhost cuponBoton">
        {dict.precios.cuponAplicar}
      </button>
      {motivo && (
        <p className="cuponEstado" role="status">
          {motivo}
        </p>
      )}
    </form>
  );
}
