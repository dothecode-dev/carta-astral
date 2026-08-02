import { redirect } from "next/navigation";

// La lectura vive dentro de la carta, debajo de la rueda y las tablas: separarlas
// obligaba a ir y volver para mirar una posición mientras se lee el texto.
// Esta ruta queda porque puede estar en el historial de alguien.
export default async function ReadingRedirect({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  redirect(`/${locale}/carta/${id}`);
}
