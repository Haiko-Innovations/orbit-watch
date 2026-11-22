import sources from "../../../docs/legal/data-sources.md?raw";
import privacy from "../../../docs/legal/privacy-notice.md?raw";
import terms from "../../../docs/legal/terms-of-use.md?raw";
import { Markdown } from "../components/Markdown";
import { type Block, parseMarkdown, title } from "../legal/markdown";

// The privacy notice and the terms of use (phase 4, step 4.4; decision P4-09), and the data
// sources (decisions P5-13, D-52): the files in docs/legal. They need no service and no
// signing in.

export type LegalDocument = "privacy" | "terms" | "data-sources";

const texts: Record<LegalDocument, string> = { privacy, terms, "data-sources": sources };

const parsed = new Map<LegalDocument, Block[]>();

function blocks(document: LegalDocument): Block[] {
  let found = parsed.get(document);
  if (!found) {
    found = parseMarkdown(texts[document]);
    parsed.set(document, found);
  }
  return found;
}

/** The page's title: its document's own heading. */
export function legalTitle(document: LegalDocument): string {
  return title(blocks(document));
}

export function LegalPage({ document }: { document: LegalDocument }) {
  return (
    <article className="legal">
      <Markdown blocks={blocks(document)} />
    </article>
  );
}
