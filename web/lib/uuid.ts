/**
 * ¿Es `id` el identificador de una carta tal como lo genera el backend?
 *
 * `Chart.uuid` es un uuid4 (`backend/api/models.py`) y Django lo devuelve en
 * minúsculas con guiones; `api/urls.py` lo recibe con `<uuid:uuid>`. Las rutas
 * de `app/api/charts/[id]/` interpolan este `id` en el path del backend: sin
 * validarlo, `..%2Fcuenta` (que Next entrega decodificado) apunta a otro
 * endpoint con la sesión de quien pidió. Lo que no tiene esta forma no es una
 * carta: 404 sin salir de la web (`noExiste`).
 */
const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function uuidValido(id: unknown): id is string {
  return typeof id === "string" && UUID4.test(id);
}

/** La misma respuesta que dan las rutas cuando el backend dice 404. */
export function noExiste(): Response {
  return Response.json({ error: "no existe" }, { status: 404 });
}
