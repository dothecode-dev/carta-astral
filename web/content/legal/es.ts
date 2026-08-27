import type { LegalContent } from "./types";

// Texto portado literal desde backend/api/legal.py. Es un documento legal
// vigente: se traduce o se corrige con intención, no se reescribe de paso.
export const legalEs: LegalContent = {
  updatedLabel: "Última actualización",

  privacy: {
    title: "Política de privacidad",
    heading: "Política de privacidad de ASTRA",
    blocks: [
      {
        kind: "p",
        text: "ASTRA es una app de **dothecode**. Esta política explica qué datos tratamos y por qué.",
      },
      { kind: "h2", text: "Qué datos recopilamos" },
      {
        kind: "ul",
        items: [
          "**Cuenta:** al entrar con Google o Apple recibimos tu identificador del proveedor y tu email. No vemos ni guardamos tu contraseña.",
          "**Datos de nacimiento:** los que cargás para calcular una carta — nombre (opcional), fecha, hora y lugar de nacimiento.",
          "**Compras:** el pago lo procesan Google Play / App Store; nosotros no vemos datos de tu tarjeta. Usamos RevenueCat como procesador para acreditar tus créditos, identificándote por tu id interno de cuenta.",
        ],
      },
      { kind: "h2", text: "Para qué los usamos" },
      {
        kind: "ul",
        items: [
          "Calcular tu carta astral y mostrarla en la app.",
          "Generar la lectura interpretativa: los datos astronómicos de la carta se procesan con **Anthropic** (el proveedor de IA) para redactar el texto. No se usan para entrenar modelos.",
          "Administrar tu saldo de créditos.",
          "**Detectar fallas y entender el uso de la app y del sitio.** Usamos **Sentry** (reportes de errores) y **PostHog** (analítica de producto). Registran acciones como iniciar sesión, crear una carta, generar una lectura o descargarla, junto con el identificador interno de tu cuenta. **Nunca les enviamos tu nombre, tu fecha, hora o lugar de nacimiento, ni el texto de tus lecturas**, y tampoco tu email. Tu dirección IP se usa únicamente para deducir el país desde el que entrás y no se almacena. En el sitio web la analítica sólo se activa si la aceptás, y podés cambiar de opinión cuando quieras desde el enlace del pie de página. Ambos servicios procesan estos datos en Estados Unidos.",
        ],
      },
      {
        kind: "p",
        text: "No vendemos tus datos, no mostramos publicidad y no hacemos perfiles con fines de marketing.",
      },
      { kind: "h2", text: "Borrado de tus datos" },
      {
        kind: "p",
        text: "Podés borrar tus cartas o tu cuenta completa desde la app (Cuenta → Borrar mis datos). El borrado de cuenta es definitivo: elimina tus datos personales, cartas, lecturas y créditos. Conservamos únicamente un **hash irreversible** del identificador de tu proveedor de login — no permite identificarte ni recuperar tus datos; sólo evita que una cuenta nueva vuelva a recibir el crédito gratuito de bienvenida.",
      },
      {
        kind: "p",
        text: "Si entraste con Apple, al borrar la cuenta también revocamos el permiso de Sign in with Apple ante Apple, de modo que ASTRA deja de estar vinculada a tu Apple ID.",
      },
      { kind: "h2", text: "Seguridad y retención" },
      {
        kind: "p",
        text: "Los datos viajan cifrados (TLS) y los tokens de sesión se guardan hasheados. Conservamos tus datos mientras tu cuenta exista.",
      },
      { kind: "h2", text: "Contacto" },
      {
        kind: "p",
        text: "Por cualquier consulta sobre tus datos, escribinos a la dirección de contacto que figura al pie.",
      },
    ],
  },

  terms: {
    title: "Términos de uso",
    heading: "Términos de uso de ASTRA",
    blocks: [
      { kind: "h2", text: "El servicio" },
      {
        kind: "p",
        text: "ASTRA calcula cartas astrales y genera lecturas interpretativas mediante inteligencia artificial. El contenido tiene fines de entretenimiento y autoconocimiento: **no constituye consejo médico, legal, financiero ni profesional** de ningún tipo, y puede contener imprecisiones propias del contenido generado automáticamente.",
      },
      { kind: "h2", text: "Cuenta" },
      {
        kind: "p",
        text: "Para usar ASTRA necesitás una cuenta (Google o Apple) y ser mayor de 13 años. Sos responsable del uso que se haga desde tu cuenta.",
      },
      { kind: "h2", text: "Créditos y compras" },
      {
        kind: "ul",
        items: [
          "Cada interpretación nueva de una carta consume **1 crédito**. Leer esa misma carta en otros idiomas no consume créditos adicionales.",
          "Los créditos se compran dentro de la app (Google Play / App Store), no vencen, no son transferibles y no tienen valor monetario fuera de la app.",
          "Las compras no son reembolsables, salvo lo que exijan la ley o las políticas de la tienda donde compraste.",
          "Si borrás tu cuenta, los créditos restantes se pierden.",
        ],
      },
      { kind: "h2", text: "Uso aceptable" },
      {
        kind: "p",
        text: "No está permitido abusar del servicio (automatizar solicitudes, revender el contenido, intentar vulnerar la seguridad).",
      },
      { kind: "h2", text: "Disponibilidad y cambios" },
      {
        kind: "p",
        text: "Podemos actualizar la app, estos términos o discontinuar el servicio; si un cambio es significativo lo vamos a comunicar en la app.",
      },
      { kind: "h2", text: "Contacto y ley aplicable" },
      {
        kind: "p",
        text: "Estos términos se rigen por las leyes de la República Argentina. Para contactarnos, usá la dirección que figura al pie.",
      },
    ],
  },
};
