// El `motivo` de una respuesta de error de las rutas de la web (cupón agotado,
// mail bloqueado…), que la pantalla traduce. Sólo de cliente: el del servidor,
// que lee el cuerpo de un `ApiError` del backend, es `motivoDe` de `lib/session`.

/** El `motivo` del cuerpo JSON, o `null` si no hay o el cuerpo no se lee. */
export async function motivoDeRespuesta(res: Response): Promise<string | null> {
  try {
    const cuerpo = (await res.json()) as { motivo?: unknown };
    return typeof cuerpo.motivo === "string" ? cuerpo.motivo : null;
  } catch {
    return null;
  }
}
