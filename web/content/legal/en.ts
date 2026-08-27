import type { LegalContent } from "./types";

// Texto portado literal desde backend/api/legal.py.
export const legalEn: LegalContent = {
  updatedLabel: "Last updated",

  privacy: {
    title: "Privacy Policy",
    heading: "ASTRA Privacy Policy",
    blocks: [
      {
        kind: "p",
        text: "ASTRA is an app by **dothecode**. This policy explains what data we process and why.",
      },
      { kind: "h2", text: "What we collect" },
      {
        kind: "ul",
        items: [
          "**Account:** when you sign in with Google or Apple we receive your provider identifier and your email. We never see or store your password.",
          "**Birth data:** what you enter to compute a chart — name (optional), date, time and place of birth.",
          "**Purchases:** payments are processed by Google Play / the App Store; we never see your card details. We use RevenueCat as a processor to credit your purchases, identified by your internal account id.",
        ],
      },
      { kind: "h2", text: "How we use it" },
      {
        kind: "ul",
        items: [
          "To compute your natal chart and show it in the app.",
          "To generate the written reading: the chart's astronomical data is processed by **Anthropic** (our AI provider) to produce the text. It is not used to train models.",
          "To manage your credit balance.",
          "**To detect failures and understand how the app and the site are used.** We use **Sentry** (error reporting) and **PostHog** (product analytics). They record actions such as signing in, creating a chart, generating a reading or downloading it, along with your internal account identifier. **We never send them your name, your birth date, time or place, or the text of your readings**, nor your email. Your IP address is used only to infer the country you are visiting from and is not stored. On the website analytics only run if you accept them, and you can change your mind at any time from the link in the footer. Both services process this data in the United States.",
        ],
      },
      {
        kind: "p",
        text: "We don't sell your data, show ads, or build marketing profiles.",
      },
      { kind: "h2", text: "Deleting your data" },
      {
        kind: "p",
        text: "You can delete your charts or your entire account from the app (Account → Delete my data). Account deletion is permanent: it removes your personal data, charts, readings and credits. We keep only an **irreversible hash** of your login provider identifier — it cannot identify you or recover your data; it only prevents a new account from receiving the free welcome credit again.",
      },
      {
        kind: "p",
        text: "If you signed in with Apple, deleting your account also revokes the Sign in with Apple grant with Apple, so ASTRA is no longer linked to your Apple ID.",
      },
      { kind: "h2", text: "Security and retention" },
      {
        kind: "p",
        text: "Data travels encrypted (TLS) and session tokens are stored hashed. We keep your data for as long as your account exists.",
      },
      { kind: "h2", text: "Contact" },
      {
        kind: "p",
        text: "For any question about your data, write to the contact address shown in the footer.",
      },
    ],
  },

  terms: {
    title: "Terms of Use",
    heading: "ASTRA Terms of Use",
    blocks: [
      { kind: "h2", text: "The service" },
      {
        kind: "p",
        text: "ASTRA computes natal charts and generates written readings using artificial intelligence. The content is for entertainment and self-reflection: **it is not medical, legal, financial or professional advice** of any kind, and may contain inaccuracies inherent to automatically generated content.",
      },
      { kind: "h2", text: "Account" },
      {
        kind: "p",
        text: "Using ASTRA requires an account (Google or Apple) and being at least 13 years old. You are responsible for activity on your account.",
      },
      { kind: "h2", text: "Credits and purchases" },
      {
        kind: "ul",
        items: [
          "Each new chart reading consumes **1 credit**. Reading that same chart in other languages costs no extra credits.",
          "Credits are purchased in-app (Google Play / App Store), never expire, are not transferable and have no monetary value outside the app.",
          "Purchases are non-refundable except as required by law or by the store's policies.",
          "If you delete your account, remaining credits are lost.",
        ],
      },
      { kind: "h2", text: "Acceptable use" },
      {
        kind: "p",
        text: "Abusing the service (automating requests, reselling content, attempting to breach security) is not allowed.",
      },
      { kind: "h2", text: "Availability and changes" },
      {
        kind: "p",
        text: "We may update the app, these terms, or discontinue the service; significant changes will be announced in the app.",
      },
      { kind: "h2", text: "Contact and governing law" },
      {
        kind: "p",
        text: "These terms are governed by the laws of Argentina. To contact us, use the address shown in the footer.",
      },
    ],
  },
};
