"use client";

import { useRef, useState } from "react";

import { VinculoForm } from "@/components/VinculoForm";
import { VinculoPreview } from "@/components/VinculoPreview";
import type { Dict, Locale } from "@/lib/i18n";
import type { TipoVinculo, VinculoPreview as Datos } from "@/lib/vinculo";

// El estado de la landing: el formulario queda siempre a la vista y el
// resultado aparece debajo. Reemplazar el formulario por el resultado (como
// hace `/nueva`) obligaría a cargar todo de nuevo para cambiar una hora, y en un
// vínculo es justo lo que la gente hace: probar con y sin la hora de la otra
// persona.

type Resultado = {
  preview: Datos;
  tipo: TipoVinculo;
  alias: { a: string; b: string };
  /** Una `key` distinta por cada cálculo: reinicia la vista contada y el aviso
   *  del botón, que son de ESE resultado y no del anterior. */
  n: number;
};

export function VinculoPagina({ locale, dict }: { locale: Locale; dict: Dict }) {
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const cuenta = useRef(0);
  const destino = useRef<HTMLDivElement>(null);

  function alLlegar(preview: Datos, tipo: TipoVinculo, alias: { a: string; b: string }) {
    cuenta.current += 1;
    setResultado({ preview, tipo, alias, n: cuenta.current });
    // En un teléfono el resultado queda debajo de dos formularios: sin llevar la
    // vista hasta ahí, quien aprieta el botón no ve que pasó algo. jsdom no
    // implementa `scrollIntoView`, de ahí el `?.`.
    requestAnimationFrame(() => destino.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }));
  }

  return (
    <>
      <VinculoForm locale={locale} dict={dict} onResultado={alLlegar} />
      <div ref={destino}>
        {resultado && (
          <VinculoPreview
            key={resultado.n}
            locale={locale}
            dict={dict}
            preview={resultado.preview}
            tipo={resultado.tipo}
            alias={resultado.alias}
          />
        )}
      </div>
    </>
  );
}
