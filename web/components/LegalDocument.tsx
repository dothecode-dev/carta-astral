import { Fragment } from "react";

import type { Block, LegalDoc } from "@/content/legal";

/** Parte el texto en **negrita** sin inyectar HTML: sale como <strong>. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <strong key={i}>{part}</strong> : <Fragment key={i}>{part}</Fragment>,
      )}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  if (block.kind === "h2") {
    return <h2 className="docH2">{block.text}</h2>;
  }
  if (block.kind === "ul") {
    return (
      <ul className="docList">
        {block.items.map((item, i) => (
          <li key={i}>
            <RichText text={item} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className="docP">
      <RichText text={block.text} />
    </p>
  );
}

export function LegalDocument({
  doc,
  updatedLabel,
  updated,
  contact,
}: {
  doc: LegalDoc;
  updatedLabel: string;
  updated: string;
  contact: string;
}) {
  return (
    <article className="doc">
      <h1 className="display docTitle">{doc.heading}</h1>
      <p className="docMeta">
        {updatedLabel}: <time dateTime={updated}>{updated}</time>
      </p>

      {doc.blocks.map((block, i) => (
        <BlockView block={block} key={i} />
      ))}

      <p className="docContact">
        <a href={`mailto:${contact}`}>{contact}</a>
      </p>
    </article>
  );
}
