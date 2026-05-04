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

// ── Approved (locked) pages — shared between Extract and Synthesise.
// Locked = re-extract / regenerate disabled for the page. Same key
// the Extract route already uses, so a page locked in Extract is
// also locked in Synthesise.

function approvedKey(slug: string): string {
  // Same key Extract has been writing since A.6 — sharing keeps the
  // two routes' lock state in sync without a migration.
  return `extract.approved.${slug}`;
}

export function loadApprovedPages(slug: string): Set<number> {
  if (!slug) return new Set();
  try {
    const raw = localStorage.getItem(approvedKey(slug));
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    return new Set(Array.isArray(arr) ? (arr as number[]) : []);
  } catch {
    return new Set();
  }
}

export function saveApprovedPages(slug: string, pages: Set<number>): void {
  if (!slug) return;
  try {
    localStorage.setItem(approvedKey(slug), JSON.stringify([...pages]));
  } catch {
    /* ignore quota / privacy errors */
  }
}
