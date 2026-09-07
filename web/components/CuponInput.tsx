"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { normalizarCupon } from "@/lib/cupon";
import type { Dict, Locale } from "@/lib/i18n";
import { track } from "@/lib/telemetry";

/**
 * El campo para escribir un código de cupón en /precios.
 *
 * No calcula nada: manda el código a la URL (`?cupon=`) y la página vuelve a
 * pintarse con los precios que devuelve el backend. Es el mismo camino que el
 * link de Instagram, así que hay una sola forma de aplicar un cupón y una sola
 * fuente del número. `estado` es lo que la página ya sabe del cupón que trae
 * la URL: válido, o por qué no.
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
  const [codigo, setCodigo] = useState(inicial ?? "");
  const [invalido, setInvalido] = useState(false);

  // Se mide cuando la página ya sabe si sirvió, no al escribirlo: es la única
  // forma de contar «quiso usar un cupón y no pudo», que es lo que importa.
  useEffect(() => {
    if (inicial && estado) track("cupon_aplicado", { codigo: inicial, resultado: estado });
  }, [inicial, estado]);

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

  const mensaje =
    invalido
      ? dict.precios.cuponMotivo.invalido
      : estado === "valido" && inicial
        ? dict.precios.cuponAplicado
            .replace("{codigo}", inicial)
            .replace("{porcentaje}", String(porcentaje ?? ""))
        : estado
          ? (dict.precios.cuponMotivo[estado] ?? dict.precios.cuponMotivo.invalido)
          : null;

  return (
    <form className="cuponForm" onSubmit={aplicar}>
      <label className="cuponLabel">
        <span>{dict.precios.cuponLabel}</span>
        <input
          className="cuponInput"
          name="cupon"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          maxLength={40}
        />
      </label>
      <button type="submit" className="btn btnGhost">
        {dict.precios.cuponAplicar}
      </button>
      {mensaje && (
        <p className={`cuponEstado${estado === "valido" && !invalido ? " cuponEstadoOk" : ""}`} role="status">
          {mensaje}
        </p>
      )}
    </form>
  );
}
