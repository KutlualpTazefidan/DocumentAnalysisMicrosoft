/**
 * HTML page-slicing utilities for the extract view.
 *
 * The backend serialises a complete HTML document with
 * ``<section data-page="{N}">`` wrappers for each extracted page
 * (see extract.py `_wrap_html`).  These helpers let the frontend
 * show only the current page without re-fetching.
 */

/**
 * Return a complete HTML document containing only the content for `page`.
 *
 * Strategy:
 *   1. Preserve the <head> block (contains the PDF <style> injection).
 *   2. Find the ``<section data-page="{page}">…</section>`` element in the body.
 *   3. Reassemble as a full document wrapping just that section.
 *   4. If no matching section exists, return a placeholder paragraph.
 */
export function sliceHtmlByPage(html: string, page: number): string {
  if (!html) {
    return buildDoc("", "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  // Extract <head> content (everything between <head> and </head>).
  const headMatch = html.match(/<head>([\s\S]*?)<\/head>/i);
  const headContent = headMatch ? headMatch[1] : "";

  // Find the <section data-page="{page}">…</section> block.
  // Attribute order may vary; allow any attributes before/after data-page.
  const sectionRe = new RegExp(
    `<section[^>]*data-page="${page}"[^>]*>([\\s\\S]*?)<\\/section>`,
    "i",
  );
  const sectionMatch = html.match(sectionRe);

  if (!sectionMatch) {
    return buildDoc(headContent, "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  const innerContent = sectionMatch[1].trim();
  if (!innerContent) {
    return buildDoc(headContent, "<p class=\"no-extraction\">Keine Extraktion fur diese Seite.</p>");
  }

  const sectionTag = `<section data-page="${page}">${innerContent}</section>`;
  return buildDoc(headContent, sectionTag);
}

function buildDoc(headContent: string, bodyContent: string): string {
  return `<!DOCTYPE html>\n<html><head>${headContent}</head><body>\n${bodyContent}\n</body></html>\n`;
}

/**
 * Rewrite ``<img src="mineru-images/foo.jpg">`` to an absolute API URL.
 *
 * The worker emits a relative ``mineru-images/{file}`` path in html.html
 * because images live on disk at ``data_root/{slug}/mineru-images/{file}``
 * and a backend route serves them. The iframe in HtmlEditor uses srcdoc,
 * whose base URL is ``about:srcdoc``, so relative paths can't reach an
 * HTTP route — we rewrite to absolute before passing the html to srcdoc.
 */
export function rewriteImageSources(
  html: string,
  apiBase: string,
  slug: string,
): string {
  if (!html || !slug) return html;
  const prefix = `${apiBase}/api/admin/docs/${encodeURIComponent(slug)}/mineru-images/`;
  return html.replace(
    /(<img[^>]*\bsrc=")mineru-images\/([^"]+)(")/gi,
    (_full, pre, file, post) => `${pre}${prefix}${file}${post}`,
  );
}
