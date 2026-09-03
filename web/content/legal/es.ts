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
        text: "ASTRA es un servicio de **dothecode, LLC**. Esta política explica qué datos tratamos y por qué.",
      },
      { kind: "h2", text: "Qué datos recopilamos" },
      {
        kind: "ul",
        items: [
          "**Cuenta:** al entrar con Google o Apple recibimos tu identificador del proveedor y tu email. No vemos ni guardamos tu contraseña.",
          "**Datos de nacimiento:** los que cargás para calcular una carta — nombre (opcional), fecha, hora y lugar de nacimiento.",
          "**Compras:** el cobro lo procesa **Stripe**, que actúa como vendedor registrado. No vemos ni guardamos los datos de tu tarjeta: de Stripe recibimos la confirmación del pago y el identificador de la compra, para darte acceso a lo que compraste.",
        ],
      },
      { kind: "h2", text: "Para qué los usamos" },
      {
        kind: "ul",
        items: [
          "Calcular tu carta astral y mostrarla en el sitio.",
          "Generar la lectura interpretativa: los datos astronómicos de la carta se procesan con **Anthropic** (el proveedor de IA) para redactar el texto. No se usan para entrenar modelos.",
          "Llevar la cuenta de los informes que tenés disponibles para leer.",
          "**Detectar fallas y entender el uso del sitio.** Usamos **Sentry** (reportes de errores) y **PostHog** (analítica de producto). Registran acciones como iniciar sesión, crear una carta, generar una lectura o descargarla, junto con el identificador interno de tu cuenta. **Nunca les enviamos tu nombre, tu fecha, hora o lugar de nacimiento, ni el texto de tus lecturas**, y tampoco tu email. Tu dirección IP se usa únicamente para deducir el país desde el que entrás y no se almacena. En el sitio web la analítica sólo se activa si la aceptás, y podés cambiar de opinión cuando quieras desde el enlace del pie de página. Ambos servicios procesan estos datos en Estados Unidos.",
        ],
      },
      {
        kind: "p",
        text: "No vendemos tus datos, no mostramos publicidad y no hacemos perfiles con fines de marketing.",
      },
      { kind: "h2", text: "Borrado de tus datos" },
      {
        kind: "p",
        text: "Podés borrar tus cartas o tu cuenta completa desde tu cuenta (Cuenta → Borrar mis datos). El borrado es definitivo: elimina tus datos personales, tus cartas, tus lecturas y lo que tengas disponible para leer. Conservamos únicamente un **hash irreversible** del identificador de tu proveedor de login — no permite identificarte ni recuperar tus datos; sólo evita que una cuenta nueva vuelva a recibir las tres lecturas gratuitas de bienvenida.",
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
        text: "Para usar ASTRA necesitás una cuenta de Google y ser mayor de 13 años. Sos responsable del uso que se haga desde tu cuenta.",
      },
      { kind: "h2", text: "Compras" },
      {
        kind: "ul",
        items: [
          "Tus **primeras tres lecturas breves son gratis**. El informe completo de una carta se compra aparte, y también podés comprar packs de tres o cinco informes.",
          "Lo que compras es el derecho a leer un informe: **no vence**, no es transferible y no tiene valor monetario fuera de ASTRA. Leer ese mismo informe en otro idioma no consume otro.",
          "El cobro lo procesa **Stripe**, que actúa como vendedor registrado (*merchant of record*): emite el comprobante, cobra el impuesto que corresponda a tu país y atiende los reclamos de la transacción.",
          "**Reembolsos:** Stripe puede reembolsar una compra dentro de los 60 días y aplica los plazos de arrepentimiento que exija tu país. Si te reembolsan una compra, se descuenta de los informes que tengas disponibles; si ya los usaste, queda como saldo pendiente que se cancela contra tu próxima compra. **Nunca retiramos un informe ya escrito.**",
          "Si borrás tu cuenta, los informes que te queden disponibles se pierden.",
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
        text: "Podemos actualizar el servicio, estos términos o discontinuarlo; si un cambio es significativo lo vamos a comunicar en el sitio.",
      },
      { kind: "h2", text: "Contacto y ley aplicable" },
      {
        kind: "p",
        text: "Estos términos se rigen por las leyes de la República Argentina. Para contactarnos, usá la dirección que figura al pie.",
      },
    ],
  },
};
