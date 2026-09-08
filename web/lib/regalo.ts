// Espejo de INSTALL_FREE_CREDITS del backend. NO se pide por red: /entrar es la
// única página que todo visitante sin sesión toca sí o sí, y hacerla depender
// del backend la deja rota cada vez que el backend esté lento, caído o con el
// cartel de mantenimiento puesto.
//
// Que los dos números coincidan lo garantiza backend/tests/test_regalo_coherente.py,
// que falla el gate si alguien cambia uno y no el otro.
export const LECTURAS_DE_REGALO = 3;
