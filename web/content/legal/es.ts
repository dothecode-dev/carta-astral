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
        text: "ASTRA es un servicio de **dothecode, LLC**. Las compras en pesos argentinos las vende **Gustavo Benito Silva** (CUIT 20-22809400-6), responsable de esa venta. Esta política explica qué datos tratamos y por qué.",
      },
      { kind: "h2", text: "Qué datos recopilamos" },
      {
        kind: "ul",
        items: [
          "**Cuenta:** al entrar con Google recibimos tu identificador de Google y tu email; con el código por mail, tu email. No vemos ni guardamos tu contraseña.",
          "**Avisos por mail:** te escribimos a tu email para mandarte el código de acceso y para avisarte de tu compra y de que tu informe está listo. Ese último mail puede incluir el nombre de la carta, tu Sol, tu Luna y tu Ascendente, y el arranque del informe.",
          "**Datos de nacimiento:** los que cargás para calcular una carta — nombre (opcional), fecha, hora y lugar de nacimiento.",
          "**Compras:** el cobro lo procesa **Stripe**, que actúa como vendedor registrado. No vemos ni guardamos los datos de tu tarjeta: de Stripe recibimos la confirmación del pago y el identificador de la compra, para darte acceso a lo que compraste. Si pagás en pesos argentinos, el cobro lo procesa **Mercado Pago**: tampoco vemos tu tarjeta, y de Mercado Pago recibimos la confirmación y el identificador del pago. Por cada compra en pesos se emite una factura electrónica ante **ARCA** (la agencia de recaudación argentina); es a consumidor final y no lleva tu nombre ni tu documento.",
          "**Comprar sin cuenta:** si abrís el pago del informe sin haber entrado, guardamos los datos de esa carta para poder entregarte el informe cuando se confirme el pago. Si el pago no se completa, la carta se borra cuando vence (a la hora de abrirlo). El email lo cargás en **Stripe**, que nos lo pasa al confirmar el pago: lo usamos para crear tu cuenta, o para acreditar la compra en la que ya tenías con ese email, y para mandarte el código de acceso. Si pagás en pesos, el email lo cargás en nuestro formulario antes de ir a Mercado Pago, y lo usamos para lo mismo.",
          "**Botón de arrepentimiento:** si lo usás, guardamos el email, el número de compra si lo escribiste, la fecha y el código del pedido, para responderlo y dejar constancia de la revocación.",
          "**Carta sin cuenta:** para mostrarte tu carta sin cuenta usamos tus datos de nacimiento en el momento y no los guardamos en nuestros servidores. Si después comprás el informe, ver «Comprar sin cuenta» más arriba.",
        ],
      },
      { kind: "h2", text: "Para qué los usamos" },
      {
        kind: "ul",
        items: [
          "Calcular tu carta astral y mostrarla en el sitio.",
          "Generar la lectura interpretativa: los datos astronómicos de la carta se procesan con **Anthropic** (el proveedor de IA) para redactar el texto. No se usan para entrenar modelos.",
          "Llevar la cuenta de los informes que tenés disponibles para leer.",
          "Enviarte esos mails: el envío lo hace **Resend**, un proveedor de envío de mails que los procesa por cuenta nuestra y sólo para entregártelos.",
          "**Detectar fallas y entender el uso del sitio.** Usamos **Sentry** (reportes de errores) y **PostHog** (analítica de producto). Registran acciones como iniciar sesión, crear una carta, generar una lectura, descargarla o completar una compra, junto con el identificador interno de tu cuenta. **Nunca les enviamos tu nombre, tu fecha, hora o lugar de nacimiento, ni el texto de tus lecturas**, y tampoco tu email. Tu dirección IP se usa únicamente para deducir el país desde el que entrás y no se almacena. En el sitio web la analítica sólo se activa si la aceptás, y podés cambiar de opinión cuando quieras desde el enlace del pie de página. **El registro de una compra completada es la excepción: lo hace nuestro servidor cuando el pago se confirma, así que no depende de esa preferencia.** Es un dato de la operación —qué producto y por cuánto—, no de tu navegación, y viaja igual que el resto: con el identificador interno de tu cuenta y sin tu email. Ambos servicios procesan estos datos en Estados Unidos.",
          "**Contar las visitas, sin cookies.** Cuando calculás una carta, nuestro servidor suma uno a un contador del día y anota por qué canal llegaste (por ejemplo, un anuncio o un buscador) y la zona horaria de tu navegador, reducida a una ciudad de referencia. Son totales por día sin nada que te identifique: no guardamos tu IP ni la página de la que venías, y no se asocian a tu cuenta.",
          "**Mostrarte los precios en tu moneda.** Para elegir en qué moneda ves los precios, nuestro servidor deduce el país a partir de tu dirección IP con una base de datos que tenemos en nuestro propio servidor (GeoLite2, de MaxMind); tu IP no sale a ningún tercero y no se almacena. Si elegís otra moneda en la página de precios, la guardamos en una cookie funcional, astra_moneda, durante un año, sólo para recordar esa elección. Este producto incluye datos de GeoLite2 creados por MaxMind, disponibles en https://www.maxmind.com.",
        ],
      },
      {
        kind: "p",
        text: "No vendemos tus datos, no mostramos publicidad y no hacemos perfiles con fines de marketing.",
      },
      { kind: "h2", text: "Borrado de tus datos" },
      {
        kind: "p",
        text: "Podés borrar tus cartas o tu cuenta completa desde tu cuenta (Cuenta → Borrar mis datos). El borrado es definitivo: elimina tus datos personales, tus cartas, tus lecturas y lo que tengas disponible para leer. Conservamos únicamente un **hash irreversible** del identificador de tu proveedor de login — no permite identificarte ni recuperar tus datos; sólo evita que se repita un regalo de bienvenida, si lo hubiera.",
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
        text: "Podés calcular y ver tu carta natal sin cuenta. Para guardar tus cartas y ver tus informes necesitás una cuenta, con Google o con tu mail. Para usar ASTRA tenés que ser mayor de 13 años. Sos responsable del uso que se haga desde tu cuenta.",
      },
      { kind: "h2", text: "Compras" },
      {
        kind: "ul",
        items: [
          "La carta natal se calcula sin costo y sin cuenta. El informe completo de una carta se compra aparte.",
          "Lo que compras es el derecho a leer un informe: **no vence**, no es transferible y no tiene valor monetario fuera de ASTRA. Leer ese mismo informe en otro idioma no consume otro.",
          "En dólares y en reales, el cobro lo procesa **Stripe**, que actúa como vendedor registrado (*merchant of record*): emite el comprobante, cobra el impuesto que corresponda a tu país y atiende los reclamos de la transacción.",
          "En pesos argentinos vende **Gustavo Benito Silva**, CUIT 20-22809400-6, monotributista: el cobro lo procesa **Mercado Pago**, el precio es final y la compra se factura con factura C.",
          "**Botón de arrepentimiento:** podés revocar la compra dentro de los 10 días corridos desde que la hiciste con el enlace «Botón de arrepentimiento» del pie de página, sin entrar a tu cuenta. En el momento te damos un código que identifica el pedido, y te escribimos para resolverlo.",
          "**Reembolsos:** en dólares y en reales, Stripe puede reembolsar una compra dentro de los 60 días y aplica los plazos de arrepentimiento que exija tu país; en pesos, el reembolso se hace por Mercado Pago. Si te reembolsan una compra, se descuenta de los informes que tengas disponibles; si ya los usaste, queda como saldo pendiente que se cancela contra tu próxima compra. **Nunca retiramos un informe ya escrito.**",
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
