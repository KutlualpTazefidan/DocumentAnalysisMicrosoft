/**
 * Per-doc current-page state shared between segment + extract routes.
 *
 * Persisted in localStorage under `doc.currentPage.{slug}` so navigating
 * between Segment and Extract preserves the page the user was viewing.
 * Survives reloads.
 */

function key(slug: string): string {
  return `doc.currentPage.${slug}`;
}

export function loadCurrentPage(slug: string): number {
  if (!slug) return 1;
  try {
    const raw = localStorage.getItem(key(slug));
    if (!raw) return 1;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n >= 1 ? n : 1;
  } catch {
    return 1;
  }
}

export function saveCurrentPage(slug: string, page: number): void {
  if (!slug || !Number.isFinite(page) || page < 1) return;
  try {
    localStorage.setItem(key(slug), String(page));
  } catch {
    /* ignore quota / privacy errors */
  }
}
