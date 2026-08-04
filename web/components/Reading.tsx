import { type Bloque, type Parte, parseReading } from "@/lib/reading";

function Texto({ partes }: { partes: Parte[] }) {
  return (
    <>
      {partes.map((p, i) =>
        p.fuerte ? <strong key={i}>{p.texto}</strong> : <span key={i}>{p.texto}</span>,
      )}
    </>
  );
}

function Bloque({ bloque }: { bloque: Bloque }) {
  if (bloque.tipo === "titulo") {
    // El nivel 1 es el título de la lectura entera, que la página ya encabeza
    // con el nombre de la persona: acá arranca en h2 para no repetir jerarquía.
    const Etiqueta = bloque.nivel === 1 ? "h2" : bloque.nivel === 2 ? "h3" : "h4";
    return <Etiqueta className="readingTitle">{bloque.texto}</Etiqueta>;
  }

  if (bloque.tipo === "lista") {
    return (
      <ul className="readingList">
        {bloque.items.map((item, i) => (
          <li key={i}>
            <Texto partes={item} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <p className="readingParagraph">
      <Texto partes={bloque.partes} />
    </p>
  );
}

/**
 * La lectura, con su markdown resuelto.
 *
 * Antes se partía por párrafos y se pintaba crudo: los títulos salían con la
 * almohadilla y las negritas con los asteriscos.
 */
export function Reading({ texto }: { texto: string }) {
  return (
    <>
      {parseReading(texto).map((bloque, i) => (
        <Bloque key={i} bloque={bloque} />
      ))}
    </>
  );
}
