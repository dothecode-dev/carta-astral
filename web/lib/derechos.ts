export type Derecho = {
  codigo_producto: string;
  cantidad_restante: number | null;
  vigente_hasta: string | null;
};

// Espejo del catálogo del backend (api/catalogo.py). Si allá se agrega un
// producto, acá se agrega su capacidad: son dos listas que tienen que
// moverse juntas, y el test de contrato de la API es el que lo caza.
//
// `pack_5_natal` no aparece acá: es lo que se compra, pero lo que otorga es
// un derecho de `informe_natal` (canje.py) — como Derecho no existe con ese
// código, no necesita capacidad propia.
const CAPACIDAD_POR_PRODUCTO: Record<string, string> = {
  lectura_breve: "leer_breve",
  informe_natal: "leer_informe",
};

export function cantidad(derechos: Derecho[], codigo: string): number {
  return derechos.find((d) => d.codigo_producto === codigo)?.cantidad_restante ?? 0;
}

export function puede(derechos: Derecho[], capacidad: string): boolean {
  return derechos.some((d) => {
    if (CAPACIDAD_POR_PRODUCTO[d.codigo_producto] !== capacidad) return false;
    if (d.cantidad_restante !== null) return d.cantidad_restante > 0;
    return d.vigente_hasta !== null && new Date(d.vigente_hasta) > new Date();
  });
}
