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
        text: "ASTRA is a service by **dothecode, LLC**. This policy explains what data we process and why.",
      },
      { kind: "h2", text: "What we collect" },
      {
        kind: "ul",
        items: [
          "**Account:** when you sign in with Google we receive your provider identifier and your email. We never see or store your password.",
          "**Birth data:** what you enter to compute a chart — name (optional), date, time and place of birth.",
          "**Purchases:** payments are processed by **Stripe**, acting as merchant of record. We never see or store your card details: from Stripe we receive the payment confirmation and the purchase identifier, so we can give you access to what you bought.",
        ],
      },
      { kind: "h2", text: "How we use it" },
      {
        kind: "ul",
        items: [
          "To compute your natal chart and show it on the site.",
          "To generate the written reading: the chart's astronomical data is processed by **Anthropic** (our AI provider) to produce the text. It is not used to train models.",
          "To keep track of the reports you have available to read.",
          "**To detect failures and understand how the site is used.** We use **Sentry** (error reporting) and **PostHog** (product analytics). They record actions such as signing in, creating a chart, generating a reading or downloading it, along with your internal account identifier. **We never send them your name, your birth date, time or place, or the text of your readings**, nor your email. Your IP address is used only to infer the country you are visiting from and is not stored. On the website analytics only run if you accept them, and you can change your mind at any time from the link in the footer. Both services process this data in the United States.",
        ],
      },
      {
        kind: "p",
        text: "We don't sell your data, show ads, or build marketing profiles.",
      },
      { kind: "h2", text: "Deleting your data" },
      {
        kind: "p",
        text: "You can delete your charts or your entire account from your account page (Account → Delete my data). Deletion is permanent: it removes your personal data, your charts, your readings and whatever you have available to read. We keep only an **irreversible hash** of your login provider identifier — it cannot identify you or recover your data; it only prevents a new account from receiving the three free welcome readings again.",
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
        text: "Using ASTRA requires a Google account and being at least 13 years old. You are responsible for activity on your account.",
      },
      { kind: "h2", text: "Purchases" },
      {
        kind: "ul",
        items: [
          "Your **first three short readings are free**. The full report for a chart is a separate purchase, and you can also buy packs of three or five reports.",
          "What you buy is the right to read a report: it **never expires**, is not transferable and has no monetary value outside ASTRA. Reading that same report in another language doesn't consume another one.",
          "Payment is processed by **Stripe**, acting as *merchant of record*: it issues the receipt, collects any tax due in your country and handles transaction enquiries.",
          "**Refunds:** Stripe may refund a purchase within 60 days and applies the cooling-off periods your country requires. If a purchase is refunded, it is deducted from the reports you have available; if you already used them, it stays as an outstanding balance settled against your next purchase. **We never take back a report that has already been written.**",
          "If you delete your account, any remaining reports are lost.",
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
        text: "We may update the service, these terms, or discontinue it; significant changes will be announced on the site.",
      },
      { kind: "h2", text: "Contact and governing law" },
      {
        kind: "p",
        text: "These terms are governed by the laws of Argentina. To contact us, use the address shown in the footer.",
      },
    ],
  },
};
