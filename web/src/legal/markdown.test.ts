import { describe, expect, it } from "vitest";
import sources from "../../../docs/legal/data-sources.md?raw";
import privacy from "../../../docs/legal/privacy-notice.md?raw";
import terms from "../../../docs/legal/terms-of-use.md?raw";
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
      ">quote without a space",
      "> a quote\nthat runs on",
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

describe("quotes", () => {
  it("read a statement that a source asks for, over several lines", () => {
    expect(parseMarkdown("Text:\n\n> One line\n> and the next.\n\nAfter.")).toEqual<Block[]>([
      { kind: "paragraph", content: [{ kind: "text", text: "Text:" }] },
      { kind: "quote", content: [{ kind: "text", text: "One line and the next." }] },
      { kind: "paragraph", content: [{ kind: "text", text: "After." }] },
    ]);
  });
});

const documents = {
  "privacy notice": privacy,
  "terms of use": terms,
  "data sources": sources,
} as const;

describe.each(Object.entries(documents))("the %s", (_, source) => {
  it("reads, with one title", () => {
    const blocks = parseMarkdown(source);
    expect(blocks.filter((b) => b.kind === "heading" && b.level === 1)).toHaveLength(1);
    expect(blocks[0]?.kind).toBe("heading");
  });

  it("links only to the service's own pages, https and email", () => {
    const hrefs = parseMarkdown(source).flatMap((block) =>
      (block.kind === "list" ? block.items.flat() : block.kind === "heading" ? [] : block.content)
        .filter((part) => part.kind === "link")
        .map((part) => (part.kind === "link" ? part.href : "")),
    );
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) {
      expect(href).toMatch(/^(https:\/\/|mailto:|#\/(privacy|terms|data-sources))/);
    }
  });
});

describe("the privacy notice", () => {
  it("names the controller, the cookie, the law and the precision", () => {
    expect(privacy).toContain("Haiko Innovations Oy");
    expect(privacy).toContain("`__Host-ow_session`");
    expect(privacy).toContain("section 205 of the Finnish Act on Electronic Communications");
    expect(privacy).toContain("two decimals of a degree");
    expect(privacy).toContain("its logs are kept for at most 30 days");
  });
});

describe("the data sources", () => {
  it("credit CelesTrak, SatChecker and SCORE with the statements they ask for", () => {
    expect(sources).toContain("CelesTrak");
    expect(sources).toContain("SatChecker is hosted at the NSF NOIRLab");
    expect(sources).toContain("SCORE is hosted at the NSF NOIRLab");
    expect(sources).toContain(
      "do not necessarily reflect the views of the NSF NOIRLab, the SKAO, the IAU",
    );
    expect(sources).toContain("Creative Commons Attribution 4.0");
  });

  it("are linked from the terms of use, which no longer call everything SIMULATED", () => {
    expect(terms).toContain("(#/data-sources)");
    expect(terms).toContain("SIMULATED data and real data side by side");
    expect(terms).not.toContain("which are SIMULATED and civilian");
  });
});
