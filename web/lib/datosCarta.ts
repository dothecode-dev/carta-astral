import type { Place } from "@/app/api/geocode/route";

// Los datos de nacimiento tal como los espera el backend, y las dos cosas que
// hay que cuidar antes de mandarlos. Vivía dentro de `NewChartForm`; Vínculo
// carga dos personas con el mismo formulario y copiarlo una vez más garantiza
// que las dos copias se vayan separando (pasó ya con la rueda).

/** Los datos de una persona, tal como los espera el backend. */
export type DatosCarta = {
  name: string | null;
  date: string;
  time: string | null;
  time_known: boolean;
  lat: number;
  lng: number;
  place_label: string;
};

export function armarDatosCarta(entrada: {
  name: string | null;
  date: string;
  time: string;
  timeUnknown: boolean;
  place: Place;
}): DatosCarta {
  const { name, date, time, timeUnknown, place } = entrada;
  return {
    name,
    date,
    // Sin hora, el backend calcula igual pero sin casas ni ángulos.
    time: timeUnknown ? null : time || null,
    time_known: !timeUnknown && Boolean(time),
    lat: place.lat,
    lng: place.lng,
    place_label: place.place_query,
  };
}

/** Qué le pasa a una fecha, con el nombre de la clave de mensaje que la explica
 *  (`dict.newChart.needDate` / `badDate`). `null` si está bien. */
export function errorDeFecha(date: string): "needDate" | "badDate" | null {
  if (!date) return "needDate";
  const year = Number(date.slice(0, 4));
  if (year < 1800 || new Date(date) > new Date()) return "badDate";
  return null;
}
