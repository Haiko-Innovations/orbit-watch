// The privacy notice, the terms of use and the data sources are Markdown files in docs/legal
// (phase 4, step 4.4; D-52), so that the same text is read on GitHub and in the application. This reads the
// small part of Markdown they use, into blocks the page renders as React elements: never
// as HTML. Anything else is refused, so a new construct fails the unit tests instead of
// showing up as stray characters.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "strong"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; content: Inline[] }
  | { kind: "paragraph"; content: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "quote"; content: Inline[] };

export class MarkdownError extends Error {}

const HEADING = /^(#{1,3}) (.+)$/;
const BULLET = /^- (.+)$/;
const NUMBERED = /^\d{1,2}\. (.+)$/;
const CONTINUATION = /^ {2,3}(\S.*)$/;
const QUOTE = /^> (.+)$/;
const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)/g;
const SAFE_HREF = /^(https:\/\/|mailto:|#\/)/;

/** The inline parts of one line or paragraph: bold, code and links. */
export function inline(text: string, where = ""): Inline[] {
  const parts: Inline[] = [];
  let at = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0;
    if (start > at) parts.push({ kind: "text", text: text.slice(at, start) });
    const [, strong, code, label, href] = match;
    if (strong !== undefined) parts.push({ kind: "strong", text: strong });
    else if (code !== undefined) parts.push({ kind: "code", text: code });
    else if (label !== undefined && href !== undefined) {
      if (!SAFE_HREF.test(href)) throw new MarkdownError(`${where}: link to ${href}`);
      parts.push({ kind: "link", text: label, href });
    }
    at = start + match[0].length;
  }
  if (at < text.length) parts.push({ kind: "text", text: text.slice(at) });
  for (const part of parts) {
    if (part.kind === "text" && /[*`<>[\]_]/.test(part.text)) {
      throw new MarkdownError(`${where}: unsupported Markdown in "${part.text.trim()}"`);
    }
  }
  return parts;
}

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] = [];

  const flush = (where: string) => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", content: inline(paragraph.join(" "), where) });
      paragraph = [];
    }
    if (list) {
      const items = list.items.map((item) => inline(item, where));
      blocks.push({ kind: "list", ordered: list.ordered, items });
      list = null;
    }
    if (quote.length) {
      blocks.push({ kind: "quote", content: inline(quote.join(" "), where) });
      quote = [];
    }
  };

  lines.forEach((raw, index) => {
    const where = `line ${index + 1}`;
    const line = raw.trimEnd();
    if (line === "") {
      flush(where);
      return;
    }
    const heading = HEADING.exec(line);
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    const continued = CONTINUATION.exec(line);
    const quoted = QUOTE.exec(line);
    if (quoted?.[1]) {
      if (paragraph.length || list) flush(where);
      quote.push(quoted[1]);
    } else if (quote.length) {
      throw new MarkdownError(`${where}: a quote ends with an empty line: ${line}`);
    } else if (heading?.[1] && heading[2]) {
      flush(where);
      const level = heading[1].length as 1 | 2 | 3;
      blocks.push({ kind: "heading", level, content: inline(heading[2], where) });
    } else if (bullet?.[1] || numbered?.[1]) {
      const ordered = numbered !== null;
      if (paragraph.length || (list && list.ordered !== ordered)) flush(where);
      list ??= { ordered, items: [] };
      list.items.push((bullet?.[1] ?? numbered?.[1]) as string);
    } else if (continued?.[1] && list) {
      const last = list.items.length - 1;
      list.items[last] = `${list.items[last]} ${continued[1]}`;
    } else if (/^\s|^[>|<]|^#|^\d+\.|^[*+] /.test(line)) {
      throw new MarkdownError(`${where}: unsupported Markdown: ${line}`);
    } else {
      if (list) flush(where);
      paragraph.push(line);
    }
  });
  flush("the end");
  return blocks;
}

/** The text of the document's first heading: its title. */
export function title(blocks: Block[]): string {
  const first = blocks.find((block) => block.kind === "heading" && block.level === 1);
  if (first?.kind !== "heading") return "";
  return first.content.map((part) => part.text).join("");
}
