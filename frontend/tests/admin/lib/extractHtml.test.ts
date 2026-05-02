import { describe, expect, it } from "vitest";
import { sliceHtmlByPage } from "../../../src/admin/lib/extractHtml";

const STYLE = "<style>body{font-family:serif}</style>";
const TWO_PAGE_HTML = `<!DOCTYPE html>
<html><head>${STYLE}</head><body>
<p data-source-box="p1-b0">Page one content</p>
<hr class="page-break">
<p data-source-box="p2-b0">Page two content</p>
</body></html>
`;

describe("sliceHtmlByPage", () => {
  it("page 1 returns first segment with head preserved", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 1);
    expect(result).toContain("Page one content");
    expect(result).not.toContain("Page two content");
    expect(result).toContain(STYLE);
    expect(result).toContain("<!DOCTYPE html>");
  });

  it("page 2 returns second segment with head preserved", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 2);
    expect(result).toContain("Page two content");
    expect(result).not.toContain("Page one content");
    expect(result).toContain(STYLE);
  });

  it("missing page returns placeholder with head preserved", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 99);
    expect(result).toContain("Keine Extraktion fur diese Seite.");
    expect(result).not.toContain("Page one content");
    expect(result).toContain(STYLE);
  });

  it("empty input returns wrapper-only with placeholder", () => {
    const result = sliceHtmlByPage("", 1);
    expect(result).toContain("Keine Extraktion fur diese Seite.");
    expect(result).toContain("<!DOCTYPE html>");
  });

  it("page-break separator is not included in sliced output", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 1);
    expect(result).not.toContain("page-break");
  });

  it("single-page doc (no hr) returns content for page 1 and placeholder for page 2", () => {
    const singlePage = `<!DOCTYPE html>\n<html><head>${STYLE}</head><body>\n<p>Only page</p>\n</body></html>\n`;
    expect(sliceHtmlByPage(singlePage, 1)).toContain("Only page");
    expect(sliceHtmlByPage(singlePage, 2)).toContain("Keine Extraktion fur diese Seite.");
  });
});
