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
        text: "ASTRA é um app da **dothecode**. Esta política explica quais dados tratamos e por quê.",
      },
      { kind: "h2", text: "O que coletamos" },
      {
        kind: "ul",
        items: [
          "**Conta:** ao entrar com Google ou Apple recebemos seu identificador do provedor e seu email. Nunca vemos nem guardamos sua senha.",
          "**Dados de nascimento:** os que você informa para calcular um mapa — nome (opcional), data, hora e lugar de nascimento.",
          "**Compras:** o pagamento é processado pelo Google Play / App Store; não vemos os dados do seu cartão. Usamos a RevenueCat como processadora para creditar suas compras, identificando você pelo id interno da conta.",
        ],
      },
      { kind: "h2", text: "Para que usamos" },
      {
        kind: "ul",
        items: [
          "Calcular seu mapa astral e mostrá-lo no app.",
          "Gerar a leitura interpretativa: os dados astronômicos do mapa são processados pela **Anthropic** (provedora de IA) para redigir o texto. Não são usados para treinar modelos.",
          "Administrar seu saldo de créditos.",
          "**Detectar falhas e entender o uso do app.** Usamos **Sentry** (relatórios de erro) e **PostHog** (analítica de produto). Eles registram ações como entrar, criar um mapa, gerar uma leitura ou compartilhá-la, junto com o identificador interno da sua conta. **Nunca enviamos a eles seu nome, sua data, hora ou local de nascimento, nem o texto das suas leituras**, tampouco seu email ou endereço IP.",
        ],
      },
      {
        kind: "p",
        text: "Não vendemos seus dados, não mostramos publicidade e não criamos perfis de marketing.",
      },
      { kind: "h2", text: "Apagar seus dados" },
      {
        kind: "p",
        text: "Você pode apagar seus mapas ou a conta inteira pelo app (Conta → Apagar meus dados). A exclusão da conta é definitiva: remove seus dados pessoais, mapas, leituras e créditos. Guardamos apenas um **hash irreversível** do identificador do seu provedor de login — ele não permite identificar você nem recuperar seus dados; só evita que uma conta nova receba de novo o crédito gratuito de boas-vindas.",
      },
      {
        kind: "p",
        text: "Se você entrou com a Apple, ao apagar a conta também revogamos a permissão de Sign in with Apple junto à Apple, de modo que o ASTRA deixa de estar vinculado ao seu Apple ID.",
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
        text: "Para usar o ASTRA você precisa de uma conta (Google ou Apple) e ter pelo menos 13 anos. Você é responsável pelo uso feito com sua conta.",
      },
      { kind: "h2", text: "Créditos e compras" },
      {
        kind: "ul",
        items: [
          "Cada leitura nova de um mapa consome **1 crédito**. Ler o mesmo mapa em outros idiomas não consome créditos adicionais.",
          "Os créditos são comprados no app (Google Play / App Store), não expiram, não são transferíveis e não têm valor monetário fora do app.",
          "As compras não são reembolsáveis, salvo o exigido por lei ou pelas políticas da loja.",
          "Se você apagar sua conta, os créditos restantes se perdem.",
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
        text: "Podemos atualizar o app, estes termos ou descontinuar o serviço; mudanças significativas serão comunicadas no app.",
      },
      { kind: "h2", text: "Contato e lei aplicável" },
      {
        kind: "p",
        text: "Estes termos são regidos pelas leis da Argentina. Para falar conosco, use o endereço que aparece no rodapé.",
      },
    ],
  },
};
