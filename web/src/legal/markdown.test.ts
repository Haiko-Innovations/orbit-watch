import { describe, expect, it } from "vitest";
import privacyFi from "../../../docs/legal/privacy-notice.fi.md?raw";
import privacyEn from "../../../docs/legal/privacy-notice.md?raw";
import termsFi from "../../../docs/legal/terms-of-use.fi.md?raw";
import termsEn from "../../../docs/legal/terms-of-use.md?raw";
import { type Block, inline, MarkdownError, parseMarkdown, title } from "./markdown";

describe("parseMarkdown", () => {
  it("reads headings, paragraphs, lists and inline parts", () => {
    const blocks = parseMarkdown(
      [
        "# Title",
        "",
        "One line",
        "and the next, with **bold**, `code` and [a link](https://example.org/x).",
        "",
        "## Part",
        "",
        "- first",
        "  continued",
        "- second [here](#/terms)",
        "",
        "1. one",
        "2. two",
      ].join("\n"),
    );
    expect(blocks).toEqual<Block[]>([
      { kind: "heading", level: 1, content: [{ kind: "text", text: "Title" }] },
      {
        kind: "paragraph",
        content: [
          { kind: "text", text: "One line and the next, with " },
          { kind: "strong", text: "bold" },
          { kind: "text", text: ", " },
          { kind: "code", text: "code" },
          { kind: "text", text: " and " },
          { kind: "link", text: "a link", href: "https://example.org/x" },
          { kind: "text", text: "." },
        ],
      },
      { kind: "heading", level: 2, content: [{ kind: "text", text: "Part" }] },
      {
        kind: "list",
        ordered: false,
        items: [
          [{ kind: "text", text: "first continued" }],
          [
            { kind: "text", text: "second " },
            { kind: "link", text: "here", href: "#/terms" },
          ],
        ],
      },
      {
        kind: "list",
        ordered: true,
        items: [[{ kind: "text", text: "one" }], [{ kind: "text", text: "two" }]],
      },
    ]);
    expect(title(blocks)).toBe("Title");
  });

  it("refuses what it does not read, rather than show it wrongly", () => {
    for (const source of [
      "<p>html</p>",
      "| a | b |",
      "> quote",
      "#### four",
      "    indented code",
      "* star list",
      "an _emphasis_",
      "a [link](javascript:alert(1))",
      "a [link](http://plain.example)",
      "a <script>",
    ]) {
      expect(() => parseMarkdown(source), source).toThrow(MarkdownError);
    }
    expect(() => inline("mailto ok [us](mailto:info@example.org)")).not.toThrow();
  });
});

const documents = {
  "privacy notice": [privacyEn, privacyFi],
  "terms of use": [termsEn, termsFi],
} as const;

/** The outline of a document: its blocks' kinds, heading levels and list lengths. */
function outline(blocks: Block[]): string[] {
  return blocks.map((block) =>
    block.kind === "heading"
      ? `h${block.level}`
      : block.kind === "list"
        ? `${block.ordered ? "ol" : "ul"}×${block.items.length}`
        : "p",
  );
}

describe.each(Object.entries(documents))("the %s", (_, [english, finnish]) => {
  it("reads in English and in Finnish, one title each", () => {
    for (const source of [english, finnish]) {
      const blocks = parseMarkdown(source);
      expect(blocks.filter((b) => b.kind === "heading" && b.level === 1)).toHaveLength(1);
      expect(blocks[0]?.kind).toBe("heading");
    }
  });

  it("has the same sections and lists in both languages", () => {
    expect(outline(parseMarkdown(finnish))).toEqual(outline(parseMarkdown(english)));
  });

  it("links only to the service's own pages, https and email", () => {
    for (const source of [english, finnish]) {
      const hrefs = parseMarkdown(source).flatMap((block) =>
        (block.kind === "list" ? block.items.flat() : block.kind === "heading" ? [] : block.content)
          .filter((part) => part.kind === "link")
          .map((part) => (part.kind === "link" ? part.href : "")),
      );
      expect(hrefs.length).toBeGreaterThan(0);
      for (const href of hrefs) expect(href).toMatch(/^(https:\/\/|mailto:|#\/(privacy|terms))/);
    }
  });
});

describe("the privacy notice", () => {
  it("names the controller, the cookie, the law and the precision", () => {
    expect(privacyEn).toContain("Haiko Innovations Oy");
    expect(privacyEn).toContain("`__Host-ow_session`");
    expect(privacyFi).toContain("`__Host-ow_session`");
    expect(privacyEn).toContain("section 205 of the Finnish Act on Electronic Communications");
    expect(privacyFi).toContain("(917/2014) 205 §");
    expect(privacyEn).toContain("two decimals of a degree");
    expect(privacyEn).toContain("its logs are kept for at most 30 days");
  });
});
