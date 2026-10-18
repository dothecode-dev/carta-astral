// Espejo de la cantidad de lecturas breves que regala una cuenta nueva. NO se
// pide por red: /entrar es la única página que todo visitante sin sesión toca
// sí o sí, y hacerla depender del backend la deja rota cada vez que el backend
// esté lento, caído o con el cartel de mantenimiento puesto.
//
// Es 0 desde el 17-10-2026: `LECTURA_BREVE_GRATIS_ENABLED` está apagado en el
// backend y ningún texto del sitio promete una lectura de regalo. Prender ese
// flag exige cambiar esto y los textos que hoy hablan de la carta y el adelanto
// como lo único gratis (un deploy de la web).
//
// Que este número coincida con el regalo efectivo del backend lo garantiza
// backend/tests/test_regalo_coherente.py, que falla el gate si alguien cambia
// uno y no el otro.
export const LECTURAS_DE_REGALO = 0;
