/**
 * Per-doc localStorage cleanup.
 *
 * Several admin features cache per-doc UI state in localStorage:
 *   - segment.approved.{slug}        — page-lock state for segment route
 *   - extract.approved.{slug}        — page-lock state for extract route
 *   - segment.confThreshold.{slug}   — default + per-page confidence thresholds
 *   - doc.currentPage.{slug}         — last-viewed page (shared between routes)
 *
 * When a doc is deleted on the backend, these stale entries should be wiped
 * so a future doc with the same slug doesn't inherit ghost state.
 *
 * Non-slug-keyed entries (admin.segment.scale, admin.extract.scale) are
 * intentionally preserved — they are global UI preferences.
 */

const PER_DOC_KEY_PREFIXES = [
  "segment.approved.",
  "extract.approved.",
  "segment.confThreshold.",
  "doc.currentPage.",
];

export function clearLocalStorageForSlug(slug: string): void {
  if (!slug) return;
  for (const prefix of PER_DOC_KEY_PREFIXES) {
    try {
      localStorage.removeItem(prefix + slug);
    } catch {
      /* ignore quota / privacy errors */
    }
  }
}
