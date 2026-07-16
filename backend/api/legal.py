"""Páginas legales públicas (privacy policy y términos) en es/en/pt.

Las exigen Google Play y App Store como URLs públicas; la app las linkea
desde Legal y el login. Contenido inline (sin templates) para mantener el
deploy simple: una sola fuente versionada.
"""

from django.http import HttpResponse

CONTACT = "info@dothecode.com"
LANGS = ("es", "en", "pt")
UPDATED = "2026-07-16"

_SHELL = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — ASTRA</title>
<style>
  body {{ background:#150715; color:#F9F7F7; font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
         line-height:1.6; max-width:720px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  h1 {{ font-weight:600; }} h2 {{ margin-top:2rem; font-weight:600; }}
  a {{ color:#D5C046; }} .meta {{ color:#A79BAF; font-size:.9rem; }}
  .langs {{ margin-bottom:2rem; font-size:.9rem; }}
</style>
</head>
<body>
<nav class="langs"><a href="?lang=es">Español</a> · <a href="?lang=en">English</a> · <a href="?lang=pt">Português</a></nav>
{body}
<p class="meta">{updated_label}: {updated} — <a href="mailto:{contact}">{contact}</a></p>
</body>
</html>"""

_UPDATED_LABEL = {"es": "Última actualización", "en": "Last updated", "pt": "Última atualização"}

_PRIVACY = {
    "es": (
        "Política de privacidad",
        """
<h1>Política de privacidad de ASTRA</h1>
<p>ASTRA es una app de <strong>dothecode</strong>. Esta política explica qué datos tratamos y por qué.</p>

<h2>Qué datos recopilamos</h2>
<ul>
<li><strong>Cuenta:</strong> al entrar con Google o Apple recibimos tu identificador del proveedor y tu email. No vemos ni guardamos tu contraseña.</li>
<li><strong>Datos de nacimiento:</strong> los que cargás para calcular una carta — nombre (opcional), fecha, hora y lugar de nacimiento.</li>
<li><strong>Compras:</strong> el pago lo procesan Google Play / App Store; nosotros no vemos datos de tu tarjeta. Usamos RevenueCat como procesador para acreditar tus créditos, identificándote por tu id interno de cuenta.</li>
</ul>

<h2>Para qué los usamos</h2>
<ul>
<li>Calcular tu carta astral y mostrarla en la app.</li>
<li>Generar la lectura interpretativa: los datos astronómicos de la carta se procesan con <strong>Anthropic</strong> (el proveedor de IA) para redactar el texto. No se usan para entrenar modelos.</li>
<li>Administrar tu saldo de créditos.</li>
</ul>
<p>No vendemos tus datos, no mostramos publicidad y no hacemos perfiles con fines de marketing.</p>

<h2>Borrado de tus datos</h2>
<p>Podés borrar tus cartas o tu cuenta completa desde la app (Cuenta → Borrar mis datos). El borrado de cuenta es definitivo: elimina tus datos personales, cartas, lecturas y créditos. Conservamos únicamente un <strong>hash irreversible</strong> del identificador de tu proveedor de login — no permite identificarte ni recuperar tus datos; sólo evita que una cuenta nueva vuelva a recibir el crédito gratuito de bienvenida.</p>

<h2>Seguridad y retención</h2>
<p>Los datos viajan cifrados (TLS) y los tokens de sesión se guardan hasheados. Conservamos tus datos mientras tu cuenta exista.</p>

<h2>Contacto</h2>
<p>Por cualquier consulta sobre tus datos: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
    "en": (
        "Privacy Policy",
        """
<h1>ASTRA Privacy Policy</h1>
<p>ASTRA is an app by <strong>dothecode</strong>. This policy explains what data we process and why.</p>

<h2>What we collect</h2>
<ul>
<li><strong>Account:</strong> when you sign in with Google or Apple we receive your provider identifier and your email. We never see or store your password.</li>
<li><strong>Birth data:</strong> what you enter to compute a chart — name (optional), date, time and place of birth.</li>
<li><strong>Purchases:</strong> payments are processed by Google Play / the App Store; we never see your card details. We use RevenueCat as a processor to credit your purchases, identified by your internal account id.</li>
</ul>

<h2>How we use it</h2>
<ul>
<li>To compute your natal chart and show it in the app.</li>
<li>To generate the written reading: the chart's astronomical data is processed by <strong>Anthropic</strong> (our AI provider) to produce the text. It is not used to train models.</li>
<li>To manage your credit balance.</li>
</ul>
<p>We don't sell your data, show ads, or build marketing profiles.</p>

<h2>Deleting your data</h2>
<p>You can delete your charts or your entire account from the app (Account → Delete my data). Account deletion is permanent: it removes your personal data, charts, readings and credits. We keep only an <strong>irreversible hash</strong> of your login provider identifier — it cannot identify you or recover your data; it only prevents a new account from receiving the free welcome credit again.</p>

<h2>Security and retention</h2>
<p>Data travels encrypted (TLS) and session tokens are stored hashed. We keep your data for as long as your account exists.</p>

<h2>Contact</h2>
<p>Any question about your data: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
    "pt": (
        "Política de privacidade",
        """
<h1>Política de privacidade do ASTRA</h1>
<p>ASTRA é um app da <strong>dothecode</strong>. Esta política explica quais dados tratamos e por quê.</p>

<h2>O que coletamos</h2>
<ul>
<li><strong>Conta:</strong> ao entrar com Google ou Apple recebemos seu identificador do provedor e seu email. Nunca vemos nem guardamos sua senha.</li>
<li><strong>Dados de nascimento:</strong> os que você informa para calcular um mapa — nome (opcional), data, hora e lugar de nascimento.</li>
<li><strong>Compras:</strong> o pagamento é processado pelo Google Play / App Store; não vemos os dados do seu cartão. Usamos a RevenueCat como processadora para creditar suas compras, identificando você pelo id interno da conta.</li>
</ul>

<h2>Para que usamos</h2>
<ul>
<li>Calcular seu mapa astral e mostrá-lo no app.</li>
<li>Gerar a leitura interpretativa: os dados astronômicos do mapa são processados pela <strong>Anthropic</strong> (provedora de IA) para redigir o texto. Não são usados para treinar modelos.</li>
<li>Administrar seu saldo de créditos.</li>
</ul>
<p>Não vendemos seus dados, não mostramos publicidade e não criamos perfis de marketing.</p>

<h2>Apagar seus dados</h2>
<p>Você pode apagar seus mapas ou a conta inteira pelo app (Conta → Apagar meus dados). A exclusão da conta é definitiva: remove seus dados pessoais, mapas, leituras e créditos. Guardamos apenas um <strong>hash irreversível</strong> do identificador do seu provedor de login — ele não permite identificar você nem recuperar seus dados; só evita que uma conta nova receba de novo o crédito gratuito de boas-vindas.</p>

<h2>Segurança e retenção</h2>
<p>Os dados trafegam cifrados (TLS) e os tokens de sessão são guardados com hash. Mantemos seus dados enquanto sua conta existir.</p>

<h2>Contato</h2>
<p>Qualquer dúvida sobre seus dados: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
}

_TERMS = {
    "es": (
        "Términos de uso",
        """
<h1>Términos de uso de ASTRA</h1>

<h2>El servicio</h2>
<p>ASTRA calcula cartas astrales y genera lecturas interpretativas mediante inteligencia artificial. El contenido tiene fines de entretenimiento y autoconocimiento: <strong>no constituye consejo médico, legal, financiero ni profesional</strong> de ningún tipo, y puede contener imprecisiones propias del contenido generado automáticamente.</p>

<h2>Cuenta</h2>
<p>Para usar ASTRA necesitás una cuenta (Google o Apple) y ser mayor de 13 años. Sos responsable del uso que se haga desde tu cuenta.</p>

<h2>Créditos y compras</h2>
<ul>
<li>Cada interpretación nueva de una carta consume <strong>1 crédito</strong>. Leer esa misma carta en otros idiomas no consume créditos adicionales.</li>
<li>Los créditos se compran dentro de la app (Google Play / App Store), no vencen, no son transferibles y no tienen valor monetario fuera de la app.</li>
<li>Las compras no son reembolsables, salvo lo que exijan la ley o las políticas de la tienda donde compraste.</li>
<li>Si borrás tu cuenta, los créditos restantes se pierden.</li>
</ul>

<h2>Uso aceptable</h2>
<p>No está permitido abusar del servicio (automatizar solicitudes, revender el contenido, intentar vulnerar la seguridad).</p>

<h2>Disponibilidad y cambios</h2>
<p>Podemos actualizar la app, estos términos o discontinuar el servicio; si un cambio es significativo lo vamos a comunicar en la app.</p>

<h2>Contacto y ley aplicable</h2>
<p>Estos términos se rigen por las leyes de la República Argentina. Contacto: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
    "en": (
        "Terms of Use",
        """
<h1>ASTRA Terms of Use</h1>

<h2>The service</h2>
<p>ASTRA computes natal charts and generates written readings using artificial intelligence. The content is for entertainment and self-reflection: <strong>it is not medical, legal, financial or professional advice</strong> of any kind, and may contain inaccuracies inherent to automatically generated content.</p>

<h2>Account</h2>
<p>Using ASTRA requires an account (Google or Apple) and being at least 13 years old. You are responsible for activity on your account.</p>

<h2>Credits and purchases</h2>
<ul>
<li>Each new chart reading consumes <strong>1 credit</strong>. Reading that same chart in other languages costs no extra credits.</li>
<li>Credits are purchased in-app (Google Play / App Store), never expire, are not transferable and have no monetary value outside the app.</li>
<li>Purchases are non-refundable except as required by law or by the store's policies.</li>
<li>If you delete your account, remaining credits are lost.</li>
</ul>

<h2>Acceptable use</h2>
<p>Abusing the service (automating requests, reselling content, attempting to breach security) is not allowed.</p>

<h2>Availability and changes</h2>
<p>We may update the app, these terms, or discontinue the service; significant changes will be announced in the app.</p>

<h2>Contact and governing law</h2>
<p>These terms are governed by the laws of Argentina. Contact: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
    "pt": (
        "Termos de uso",
        """
<h1>Termos de uso do ASTRA</h1>

<h2>O serviço</h2>
<p>ASTRA calcula mapas astrais e gera leituras interpretativas usando inteligência artificial. O conteúdo tem fins de entretenimento e autoconhecimento: <strong>não constitui aconselhamento médico, jurídico, financeiro nem profissional</strong> de nenhum tipo, e pode conter imprecisões próprias de conteúdo gerado automaticamente.</p>

<h2>Conta</h2>
<p>Para usar o ASTRA você precisa de uma conta (Google ou Apple) e ter pelo menos 13 anos. Você é responsável pelo uso feito com sua conta.</p>

<h2>Créditos e compras</h2>
<ul>
<li>Cada leitura nova de um mapa consome <strong>1 crédito</strong>. Ler o mesmo mapa em outros idiomas não consome créditos adicionais.</li>
<li>Os créditos são comprados no app (Google Play / App Store), não expiram, não são transferíveis e não têm valor monetário fora do app.</li>
<li>As compras não são reembolsáveis, salvo o exigido por lei ou pelas políticas da loja.</li>
<li>Se você apagar sua conta, os créditos restantes se perdem.</li>
</ul>

<h2>Uso aceitável</h2>
<p>Não é permitido abusar do serviço (automatizar solicitações, revender o conteúdo, tentar violar a segurança).</p>

<h2>Disponibilidade e mudanças</h2>
<p>Podemos atualizar o app, estes termos ou descontinuar o serviço; mudanças significativas serão comunicadas no app.</p>

<h2>Contato e lei aplicável</h2>
<p>Estes termos são regidos pelas leis da Argentina. Contato: <a href="mailto:info@dothecode.com">info@dothecode.com</a>.</p>
""",
    ),
}

_DOCS = {"privacy": _PRIVACY, "terms": _TERMS}


def legal_page(request, doc: str):
    lang = request.GET.get("lang", "es")
    if lang not in LANGS:
        lang = "es"
    title, body = _DOCS[doc][lang]
    html = _SHELL.format(
        lang=lang,
        title=title,
        body=body,
        updated_label=_UPDATED_LABEL[lang],
        updated=UPDATED,
        contact=CONTACT,
    )
    return HttpResponse(html)
