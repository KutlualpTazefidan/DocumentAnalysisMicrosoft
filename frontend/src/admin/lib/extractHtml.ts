/**
 * HTML page-slicing utilities for the extract view.
 *
 * The backend serialises a complete HTML document with `<hr class="page-break">`
 * separators between pages (see extract.py `_wrap_html`).  These helpers let the
 * frontend show only the current page without re-fetching.
 */

/**
 * Return a complete HTML document containing only the content for `page`.
 *
 * Strategy:
 *   1. Preserve the <head> block (contains the PDF <style> injection) and the
 *      opening <body> tag verbatim as the "wrapper".
 *   2. Split the body content on `<hr class="page-break">` separators.
 *      Segment index 0 = page 1, index 1 = page 2, …
 *   3. Reassemble as a full document with only the requested segment.
 *   4. If the page has no segment (no extraction yet), return the wrapper with
 *      a placeholder paragraph.
 */
export function sliceHtmlByPage(html: string, page: number): string {
  if (!html) {
    return buildDoc("", "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  // Extract <head> content (everything between <head> and </head>).
  const headMatch = html.match(/<head>([\s\S]*?)<\/head>/i);
  const headContent = headMatch ? headMatch[1] : "";

  // Extract <body> content (everything between <body> and </body>).
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (!bodyMatch) {
    return buildDoc(headContent, "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  const bodyContent = bodyMatch[1];

  // Split on the page-break separator.  The pattern must match the exact
  // markup emitted by _wrap_html: `<hr class="page-break">`.
  const segments = bodyContent.split(/<hr\s+class="page-break">/i);

  // page is 1-indexed; segments[0] is page 1.
  const idx = page - 1;
  if (idx < 0 || idx >= segments.length) {
    return buildDoc(headContent, "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  const segment = segments[idx].trim();
  if (!segment) {
    return buildDoc(headContent, "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  return buildDoc(headContent, segment);
}

function buildDoc(headContent: string, bodyContent: string): string {
  return `<!DOCTYPE html>\n<html><head>${headContent}</head><body>\n${bodyContent}\n</body></html>\n`;
}
