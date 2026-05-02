import { describe, expect, it } from "vitest";
import { sliceHtmlByPage } from "../../../src/admin/lib/extractHtml";

const STYLE = "<style>body{font-family:serif}</style>";

const TWO_PAGE_HTML = `<!DOCTYPE html>
<html><head>${STYLE}</head><body>
<section data-page="1">
<p data-source-box="p1-b0">Page one content</p>
</section>
<section data-page="2">
<p data-source-box="p2-b0">Page two content</p>
</section>
</body></html>
`;

describe("sliceHtmlByPage", () => {
  it("page 1 returns first section with head preserved", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 1);
    expect(result).toContain("Page one content");
    expect(result).not.toContain("Page two content");
    expect(result).toContain(STYLE);
    expect(result).toContain("<!DOCTYPE html>");
  });

  it("page 2 returns second section with head preserved", () => {
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

  it("section wrapper is preserved in sliced output", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 1);
    expect(result).toContain('data-page="1"');
    expect(result).not.toContain('data-page="2"');
  });

  it("single-page doc (page 8 only) returns content for page 8 and placeholder for page 1", () => {
    const singlePage = `<!DOCTYPE html>\n<html><head>${STYLE}</head><body>\n<section data-page="8">\n<p>Only page eight</p>\n</section>\n</body></html>\n`;
    expect(sliceHtmlByPage(singlePage, 8)).toContain("Only page eight");
    expect(sliceHtmlByPage(singlePage, 1)).toContain("Keine Extraktion fur diese Seite.");
  });

  it("page 3 from doc with sections [1, 2, 4] returns placeholder", () => {
    const sparse = `<!DOCTYPE html>\n<html><head>${STYLE}</head><body>\n<section data-page="1"><p>p1</p></section>\n<section data-page="2"><p>p2</p></section>\n<section data-page="4"><p>p4</p></section>\n</body></html>\n`;
    const result = sliceHtmlByPage(sparse, 3);
    expect(result).toContain("Keine Extraktion fur diese Seite.");
    expect(result).not.toContain("<p>p1</p>");
  });

  it("head styling is preserved in placeholder output", () => {
    const result = sliceHtmlByPage(TWO_PAGE_HTML, 99);
    expect(result).toContain(STYLE);
    expect(result).toContain("<!DOCTYPE html>");
  });
});
