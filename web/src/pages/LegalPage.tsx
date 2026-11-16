import privacyFi from "../../../docs/legal/privacy-notice.fi.md?raw";
import privacyEn from "../../../docs/legal/privacy-notice.md?raw";
import termsFi from "../../../docs/legal/terms-of-use.fi.md?raw";
import termsEn from "../../../docs/legal/terms-of-use.md?raw";
import { Markdown } from "../components/Markdown";
import { type Block, parseMarkdown, title } from "../legal/markdown";
import { type Language, paths } from "../router";
import { strings } from "../strings";

// The privacy notice and the terms of use (phase 4, step 4.4; decision P4-09): the files in
// docs/legal, in English and Finnish. They need no service and no signing in.

export type LegalDocument = "privacy" | "terms";

const sources: Record<LegalDocument, Record<Language, string>> = {
  privacy: { en: privacyEn, fi: privacyFi },
  terms: { en: termsEn, fi: termsFi },
};

const parsed = new Map<string, Block[]>();

function blocks(document: LegalDocument, lang: Language): Block[] {
  const key = `${document}/${lang}`;
  let found = parsed.get(key);
  if (!found) {
    found = parseMarkdown(sources[document][lang]);
    parsed.set(key, found);
  }
  return found;
}

/** The page's title: its document's own heading, in its own language. */
export function legalTitle(document: LegalDocument, lang: Language): string {
  return title(blocks(document, lang));
}

export function LegalPage({ document, lang }: { document: LegalDocument; lang: Language }) {
  const other: Language = lang === "en" ? "fi" : "en";
  return (
    <article className="legal" lang={lang}>
      <p className="legal-language">
        <a href={paths.legal(document, other)} hrefLang={other} lang={other}>
          {other === "fi" ? strings.legal.inFinnish : strings.legal.inEnglish}
        </a>
      </p>
      <Markdown blocks={blocks(document, lang)} />
    </article>
  );
}
