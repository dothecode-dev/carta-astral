// Liveness para Coolify, igual que el /healthz/ del backend: responde que el
// proceso está vivo y no toca nada más.
// Dinámico a propósito: un healthcheck cacheado no dice nada del proceso vivo.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
