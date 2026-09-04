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
        text: "ASTRA é um serviço da **dothecode, LLC**. Esta política explica quais dados tratamos e por quê.",
      },
      { kind: "h2", text: "O que coletamos" },
      {
        kind: "ul",
        items: [
          "**Conta:** ao entrar com Google recebemos seu identificador do provedor e seu email. Nunca vemos nem guardamos sua senha.",
          "**Dados de nascimento:** os que você informa para calcular um mapa — nome (opcional), data, hora e lugar de nascimento.",
          "**Compras:** o pagamento é processado pela **Stripe**, que atua como vendedora registrada. Não vemos nem guardamos os dados do seu cartão: da Stripe recebemos a confirmação do pagamento e o identificador da compra, para liberar o que você comprou.",
        ],
      },
      { kind: "h2", text: "Para que usamos" },
      {
        kind: "ul",
        items: [
          "Calcular seu mapa astral e mostrá-lo no site.",
          "Gerar a leitura interpretativa: os dados astronômicos do mapa são processados pela **Anthropic** (provedora de IA) para redigir o texto. Não são usados para treinar modelos.",
          "Controlar os relatórios que você tem disponíveis para ler.",
          "**Detectar falhas e entender o uso do site.** Usamos **Sentry** (relatórios de erro) e **PostHog** (analítica de produto). Eles registram ações como entrar, criar um mapa, gerar uma leitura, baixá-la ou concluir uma compra, junto com o identificador interno da sua conta. **Nunca enviamos a eles seu nome, sua data, hora ou local de nascimento, nem o texto das suas leituras**, tampouco seu email. Seu endereço IP é usado apenas para deduzir o país de onde você acessa e não é armazenado. No site a analítica só é ativada se você aceitar, e você pode mudar de ideia quando quiser pelo link no rodapé. **O registro de uma compra concluída é a exceção: quem faz isso é o nosso servidor quando o pagamento é confirmado, então não depende dessa preferência.** É um dado da operação —qual produto e por quanto—, não da sua navegação, e viaja como o resto: com o identificador interno da sua conta e sem o seu email. Ambos os serviços processam esses dados nos Estados Unidos.",
        ],
      },
      {
        kind: "p",
        text: "Não vendemos seus dados, não mostramos publicidade e não criamos perfis de marketing.",
      },
      { kind: "h2", text: "Apagar seus dados" },
      {
        kind: "p",
        text: "Você pode apagar seus mapas ou a conta inteira pela sua conta (Conta → Apagar meus dados). A exclusão é definitiva: remove seus dados pessoais, seus mapas, suas leituras e o que você tiver disponível para ler. Guardamos apenas um **hash irreversível** do identificador do seu provedor de login — ele não permite identificar você nem recuperar seus dados; só evita que uma conta nova receba de novo as três leituras gratuitas de boas-vindas.",
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
        text: "Para usar o ASTRA você precisa de uma conta do Google e ter pelo menos 13 anos. Você é responsável pelo uso feito com sua conta.",
      },
      { kind: "h2", text: "Compras" },
      {
        kind: "ul",
        items: [
          "Suas **três primeiras leituras breves são gratuitas**. O relatório completo de um mapa é comprado à parte, e você também pode comprar pacotes de três ou cinco relatórios.",
          "O que você compra é o direito de ler um relatório: **não expira**, não é transferível e não tem valor monetário fora do ASTRA. Ler esse mesmo relatório em outro idioma não consome outro.",
          "O pagamento é processado pela **Stripe**, que atua como vendedora registrada (*merchant of record*): emite o comprovante, cobra o imposto devido no seu país e atende as reclamações da transação.",
          "**Reembolsos:** a Stripe pode reembolsar uma compra em até 60 dias e aplica os prazos de arrependimento exigidos no seu país. Se uma compra for reembolsada, ela é descontada dos relatórios que você tem disponíveis; se você já os usou, fica como saldo pendente que é abatido na próxima compra. **Nunca retiramos um relatório já escrito.**",
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
