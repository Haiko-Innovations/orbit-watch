import type { ReactNode } from "react";
import type { Block, Inline } from "../legal/markdown";

function Parts({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((part, index) => {
        const key = `${index}-${part.kind}`;
        switch (part.kind) {
          case "strong":
            return <strong key={key}>{part.text}</strong>;
          case "code":
            return <code key={key}>{part.text}</code>;
          case "link":
            return part.href.startsWith("https://") ? (
              <a key={key} href={part.href} rel="noopener noreferrer">
                {part.text}
              </a>
            ) : (
              <a key={key} href={part.href}>
                {part.text}
              </a>
            );
          default:
            return part.text;
        }
      })}
    </>
  );
}

/** Blocks read by legal/markdown.ts, as elements; the first heading takes the focus that
 * every page's heading takes (App.tsx). */
export function Markdown({ blocks }: { blocks: Block[] }) {
  const elements: ReactNode[] = blocks.map((block, index) => {
    const key = `${index}-${block.kind}`;
    switch (block.kind) {
      case "heading": {
        const content = <Parts parts={block.content} />;
        if (block.level === 1)
          return (
            <h1 key={key} tabIndex={-1}>
              {content}
            </h1>
          );
        return block.level === 2 ? <h2 key={key}>{content}</h2> : <h3 key={key}>{content}</h3>;
      }
      case "paragraph":
        return (
          <p key={key}>
            <Parts parts={block.content} />
          </p>
        );
      case "list": {
        const items = block.items.map((item, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: a fixed document, never reordered
          <li key={i}>
            <Parts parts={item} />
          </li>
        ));
        return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
      }
      default:
        return null;
    }
  });
  return <>{elements}</>;
}
