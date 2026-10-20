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
        text: "ASTRA is a service by **dothecode, LLC**. Purchases in Argentine pesos are sold by **Gustavo Benito Silva** (CUIT 20-22809400-6), who is responsible for that sale. This policy explains what data we process and why.",
      },
      { kind: "h2", text: "What we collect" },
      {
        kind: "ul",
        items: [
          "**Account:** when you sign in with Google we receive your Google identifier and your email; with the email code, your email. We never see or store your password.",
          "**Email notices:** we write to your email to send you the access code and to let you know about your purchase and that your report is ready. That last email may include the chart's name, your Sun, Moon and Ascendant signs, and the opening of the report.",
          "**Birth data:** what you enter to compute a chart — name (optional), date, time and place of birth.",
          "**Purchases:** payments are processed by **Stripe**, acting as merchant of record. We never see or store your card details: from Stripe we receive the payment confirmation and the purchase identifier, so we can give you access to what you bought. If you pay in Argentine pesos, the payment is processed by **Mercado Pago**: we don't see your card there either, and from Mercado Pago we receive the payment confirmation and identifier. Each purchase in pesos gets an electronic invoice issued with **ARCA** (Argentina's tax agency); it is issued to a final consumer and carries neither your name nor your ID.",
          "**Buying without an account:** if you open the payment for the report without signing in, we store that chart's data so we can deliver the report once the payment is confirmed. If the payment isn't completed, the chart is deleted when the checkout expires (one hour after opening it). You enter your email in **Stripe**, which passes it to us when the payment is confirmed: we use it to create your account, or to credit the purchase to the account you already had with that email, and to send you the access code. If you pay in pesos, you enter your email in our form before going to Mercado Pago, and we use it for the same purposes; and since a Mercado Pago payment can be confirmed late, if it isn't completed the chart is kept for up to 26 hours after you opened the payment and then deleted.",
          "**Cancellation button:** if you use it, we store the email, the purchase number if you entered it, the date and the request code, to answer it and keep a record of the cancellation.",
          "**Chart without an account:** to show you your chart without an account we use your birth details at that moment and don't store them on our servers. If you then buy the report, see «Buying without an account» above.",
        ],
      },
      { kind: "h2", text: "How we use it" },
      {
        kind: "ul",
        items: [
          "To compute your natal chart and show it on the site.",
          "To generate the written reading: the chart's astronomical data is processed by **Anthropic** (our AI provider) to produce the text. It is not used to train models.",
          "To keep track of the reports you have available to read.",
          "To send you those emails: they are delivered by **Resend**, an email delivery provider that processes them on our behalf and only to deliver them to you.",
          "**To detect failures and understand how the site is used.** We use **Sentry** (error reporting) and **PostHog** (product analytics). They record actions such as signing in, creating a chart, generating a reading, downloading it or completing a purchase, along with your internal account identifier. **We never send them your name, your birth date, time or place, or the text of your readings**, nor your email. Your IP address is used only to infer the country you are visiting from and is not stored. On the website analytics only run if you accept them, and you can change your mind at any time from the link in the footer. **Recording a completed purchase is the exception: our server does it when the payment is confirmed, so it does not depend on that preference.** It is data about the transaction —which product and for how much—, not about your browsing, and it travels like the rest: with your internal account identifier and without your email. Both services process this data in the United States.",
          "**Counting visits, without cookies.** Every page you open adds one to a daily counter on our server, which records the section of the site, which channel you came from (for example, an ad or a search engine) and your country, worked out from your IP address without storing it. When you calculate a chart it also adds to chart counters, with the channel, the country and your browser's time zone, reduced to a reference city. If you calculated it without an account, it also adds to other counters when you open the chart's data, reach the end, press buy (with the currency of the price you saw), leave your email to pay in pesos or go back. These are daily totals with nothing that identifies you: we do not store your IP or the page you came from, and they are not linked to your account.",
          "**Showing prices in your currency.** To choose which currency you see prices in, our server works out your country from your IP address using a database kept on our own server (GeoLite2, by MaxMind); your IP is not sent to any third party and is not stored. If you pick another currency on the pricing page, we keep that choice in a functional cookie, astra_moneda, for one year, only to remember it. This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com.",
          "**Showing the Data Fiscal seal.** In the site footer we show the Data Fiscal logo (Form 960/D) of **ARCA**, the Argentine tax authority, which requires it from anyone selling online. The image loads from ARCA's servers, so ARCA receives your IP address and the usual technical details of your browser when you open a page on the site. We send it nothing else.",
        ],
      },
      {
        kind: "p",
        text: "We don't sell your data, show ads, or build marketing profiles.",
      },
      { kind: "h2", text: "Deleting your data" },
      {
        kind: "p",
        text: "You can delete your charts or your entire account from your account page (Account → Delete my data). Deletion is permanent: it removes your personal data, your charts, your readings and whatever you have available to read. We keep only an **irreversible hash** of your login provider identifier — it cannot identify you or recover your data; it only prevents a welcome gift from being repeated, if there is one.",
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
        text: "You can calculate and see your birth chart without an account. To save your charts and see your reports you need an account, with Google or with your email. To use ASTRA you must be at least 13 years old. You are responsible for activity on your account.",
      },
      { kind: "h2", text: "Purchases" },
      {
        kind: "ul",
        items: [
          "Your birth chart is calculated at no cost and without an account. The full report for a chart is a separate purchase.",
          "What you buy is the right to read a report: it **never expires**, is not transferable and has no monetary value outside ASTRA. Reading that same report in another language doesn't consume another one.",
          "In US dollars and Brazilian reais, payment is processed by **Stripe**, acting as *merchant of record*: it issues the receipt, collects any tax due in your country and handles transaction enquiries.",
          "In Argentine pesos the seller is **Gustavo Benito Silva**, CUIT 20-22809400-6, a registered sole trader (monotributista): payment is processed by **Mercado Pago**, the price is final and the purchase is invoiced with a type C invoice.",
          "**Cancellation button:** you can cancel a purchase within 10 calendar days of making it with the «Cancellation button» link in the footer, without signing in. We give you a code that identifies the request right away, and we write to you to resolve it.",
          "**Refunds:** in US dollars and reais, Stripe may refund a purchase within 60 days and applies the cooling-off periods your country requires; in pesos, refunds are made through Mercado Pago. If a purchase is refunded, it is deducted from the reports you have available; if you already used them, it stays as an outstanding balance settled against your next purchase. **We never take back a report that has already been written.**",
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
