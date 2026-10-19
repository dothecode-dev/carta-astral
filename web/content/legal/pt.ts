import type { LegalContent } from "./types";

// Texto portado literal desde backend/api/legal.py.
export const legalPt: LegalContent = {
  updatedLabel: "Última atualização",

  privacy: {
    title: "Política de privacidade",
    heading: "Política de privacidade do ASTRA",
    blocks: [
      {
        kind: "p",
        text: "ASTRA é um serviço da **dothecode, LLC**. As compras em pesos argentinos são vendidas por **Gustavo Benito Silva** (CUIT 20-22809400-6), responsável por essa venda. Esta política explica quais dados tratamos e por quê.",
      },
      { kind: "h2", text: "O que coletamos" },
      {
        kind: "ul",
        items: [
          "**Conta:** ao entrar com Google recebemos seu identificador do Google e seu email; com o código por email, seu email. Nunca vemos nem guardamos sua senha.",
          "**Avisos por e-mail:** escrevemos para o seu e-mail para enviar o código de acesso e avisar sobre a sua compra e que o seu relatório está pronto. Esse último e-mail pode incluir o nome do mapa, o seu Sol, a sua Lua e o seu Ascendente, e o início do relatório.",
          "**Dados de nascimento:** os que você informa para calcular um mapa — nome (opcional), data, hora e lugar de nascimento.",
          "**Compras:** o pagamento é processado pela **Stripe**, que atua como vendedora registrada. Não vemos nem guardamos os dados do seu cartão: da Stripe recebemos a confirmação do pagamento e o identificador da compra, para liberar o que você comprou. Se você pagar em pesos argentinos, o pagamento é processado pelo **Mercado Pago**: também não vemos seu cartão, e do Mercado Pago recebemos a confirmação e o identificador do pagamento. Para cada compra em pesos é emitida uma nota fiscal eletrônica junto à **ARCA** (a agência de arrecadação argentina); ela é emitida a consumidor final e não leva seu nome nem seu documento.",
          "**Comprar sem conta:** se você abrir o pagamento do relatório sem ter entrado, guardamos os dados desse mapa para poder entregar o relatório quando o pagamento for confirmado. Se o pagamento não for concluído, o mapa é apagado quando o checkout expira (uma hora depois de aberto). Você informa seu e-mail no **Stripe**, que nos repassa quando o pagamento é confirmado: usamos esse e-mail para criar sua conta, ou para creditar a compra na conta que você já tinha com ele, e para enviar o código de acesso. Se você pagar em pesos, informa o e-mail no nosso formulário antes de ir ao Mercado Pago, e o usamos para o mesmo; e como um pagamento do Mercado Pago pode ser confirmado mais tarde, se não for concluído o mapa fica guardado por até 26 horas depois de aberto o pagamento e depois é apagado.",
          "**Botão de arrependimento:** se você usá-lo, guardamos o e-mail, o número da compra se você o informou, a data e o código do pedido, para respondê-lo e registrar o cancelamento.",
          "**Mapa sem conta:** para mostrar seu mapa sem conta usamos seus dados de nascimento no momento e não os guardamos nos nossos servidores. Se depois você comprar o relatório, veja «Comprar sem conta» acima.",
        ],
      },
      { kind: "h2", text: "Para que usamos" },
      {
        kind: "ul",
        items: [
          "Calcular seu mapa astral e mostrá-lo no site.",
          "Gerar a leitura interpretativa: os dados astronômicos do mapa são processados pela **Anthropic** (provedora de IA) para redigir o texto. Não são usados para treinar modelos.",
          "Controlar os relatórios que você tem disponíveis para ler.",
          "Enviar esses e-mails: o envio é feito pela **Resend**, um provedor de envio de e-mails que os processa por nossa conta e apenas para entregá-los a você.",
          "**Detectar falhas e entender o uso do site.** Usamos **Sentry** (relatórios de erro) e **PostHog** (analítica de produto). Eles registram ações como entrar, criar um mapa, gerar uma leitura, baixá-la ou concluir uma compra, junto com o identificador interno da sua conta. **Nunca enviamos a eles seu nome, sua data, hora ou local de nascimento, nem o texto das suas leituras**, tampouco seu email. Seu endereço IP é usado apenas para deduzir o país de onde você acessa e não é armazenado. No site a analítica só é ativada se você aceitar, e você pode mudar de ideia quando quiser pelo link no rodapé. **O registro de uma compra concluída é a exceção: quem faz isso é o nosso servidor quando o pagamento é confirmado, então não depende dessa preferência.** É um dado da operação —qual produto e por quanto—, não da sua navegação, e viaja como o resto: com o identificador interno da sua conta e sem o seu email. Ambos os serviços processam esses dados nos Estados Unidos.",
          "**Contar as visitas, sem cookies.** Quando você calcula uma carta, nosso servidor soma um a um contador do dia e anota por qual canal você chegou (por exemplo, um anúncio ou um buscador) e o fuso horário do seu navegador, reduzido a uma cidade de referência. São totais por dia sem nada que identifique você: não guardamos seu IP nem a página de onde você veio, e eles não são associados à sua conta.",
          "**Mostrar os preços na sua moeda.** Para escolher em que moeda você vê os preços, nosso servidor deduz o país a partir do seu endereço IP com uma base de dados mantida no nosso próprio servidor (GeoLite2, da MaxMind); seu IP não é enviado a nenhum terceiro e não é armazenado. Se você escolher outra moeda na página de preços, guardamos essa escolha em um cookie funcional, astra_moneda, por um ano, só para lembrá-la. Este produto inclui dados GeoLite2 criados pela MaxMind, disponíveis em https://www.maxmind.com.",
          "**Mostrar o selo de Data Fiscal.** No rodapé do site mostramos o logotipo do Data Fiscal (Formulário 960/D) da **ARCA**, o órgão arrecadador argentino, que o exige de quem vende pela internet. A imagem é carregada dos servidores da ARCA, então a ARCA recebe seu endereço IP e os dados técnicos habituais do seu navegador quando você abre uma página do site. Nós não enviamos mais nada a ela.",
        ],
      },
      {
        kind: "p",
        text: "Não vendemos seus dados, não mostramos publicidade e não criamos perfis de marketing.",
      },
      { kind: "h2", text: "Apagar seus dados" },
      {
        kind: "p",
        text: "Você pode apagar seus mapas ou a conta inteira pela sua conta (Conta → Apagar meus dados). A exclusão é definitiva: remove seus dados pessoais, seus mapas, suas leituras e o que você tiver disponível para ler. Guardamos apenas um **hash irreversível** do identificador do seu provedor de login — ele não permite identificar você nem recuperar seus dados; só evita que um presente de boas-vindas se repita, se houver.",
      },
      { kind: "h2", text: "Segurança e retenção" },
      {
        kind: "p",
        text: "Os dados trafegam cifrados (TLS) e os tokens de sessão são guardados com hash. Mantemos seus dados enquanto sua conta existir.",
      },
      { kind: "h2", text: "Contato" },
      {
        kind: "p",
        text: "Para qualquer dúvida sobre seus dados, escreva para o endereço de contato que aparece no rodapé.",
      },
    ],
  },

  terms: {
    title: "Termos de uso",
    heading: "Termos de uso do ASTRA",
    blocks: [
      { kind: "h2", text: "O serviço" },
      {
        kind: "p",
        text: "ASTRA calcula mapas astrais e gera leituras interpretativas usando inteligência artificial. O conteúdo tem fins de entretenimento e autoconhecimento: **não constitui aconselhamento médico, jurídico, financeiro nem profissional** de nenhum tipo, e pode conter imprecisões próprias de conteúdo gerado automaticamente.",
      },
      { kind: "h2", text: "Conta" },
      {
        kind: "p",
        text: "Você pode calcular e ver seu mapa natal sem conta. Para guardar seus mapas e ver seus relatórios é preciso uma conta, com o Google ou com o seu e-mail. Para usar o ASTRA você precisa ter pelo menos 13 anos. Você é responsável pelo uso feito com sua conta.",
      },
      { kind: "h2", text: "Compras" },
      {
        kind: "ul",
        items: [
          "O mapa natal é calculado sem custo e sem conta. O relatório completo de um mapa é comprado à parte.",
          "O que você compra é o direito de ler um relatório: **não expira**, não é transferível e não tem valor monetário fora do ASTRA. Ler esse mesmo relatório em outro idioma não consome outro.",
          "Em dólares e em reais, o pagamento é processado pela **Stripe**, que atua como vendedora registrada (*merchant of record*): emite o comprovante, cobra o imposto devido no seu país e atende as reclamações da transação.",
          "Em pesos argentinos o vendedor é **Gustavo Benito Silva**, CUIT 20-22809400-6, monotributista: o pagamento é processado pelo **Mercado Pago**, o preço é final e a compra é faturada com nota fiscal tipo C.",
          "**Botão de arrependimento:** você pode cancelar a compra em até 10 dias corridos depois de feita, pelo link «Botão de arrependimento» do rodapé, sem entrar na sua conta. Na hora damos um código que identifica o pedido, e escrevemos para resolver.",
          "**Reembolsos:** em dólares e em reais, a Stripe pode reembolsar uma compra em até 60 dias e aplica os prazos de arrependimento exigidos no seu país; em pesos, o reembolso é feito pelo Mercado Pago. Se uma compra for reembolsada, ela é descontada dos relatórios que você tem disponíveis; se você já os usou, fica como saldo pendente que é abatido na próxima compra. **Nunca retiramos um relatório já escrito.**",
          "Se você apagar sua conta, os relatórios restantes se perdem.",
        ],
      },
      { kind: "h2", text: "Uso aceitável" },
      {
        kind: "p",
        text: "Não é permitido abusar do serviço (automatizar solicitações, revender o conteúdo, tentar violar a segurança).",
      },
      { kind: "h2", text: "Disponibilidade e mudanças" },
      {
        kind: "p",
        text: "Podemos atualizar o serviço, estes termos ou descontinuá-lo; mudanças significativas serão comunicadas no site.",
      },
      { kind: "h2", text: "Contato e lei aplicável" },
      {
        kind: "p",
        text: "Estes termos são regidos pelas leis da Argentina. Para falar conosco, use o endereço que aparece no rodapé.",
      },
    ],
  },
};
