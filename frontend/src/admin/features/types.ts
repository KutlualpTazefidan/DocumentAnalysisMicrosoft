import type { ComponentType } from "react";

/** A workspace tab, self-described by its own feature module. The registry
 * auto-discovers these (admin/features/<key>/tab.tsx default export), so adding
 * a tab edits zero shared files. */
export interface TabDescriptor {
  key: string; // URL segment + identity, e.g. "extract"
  label: string; // bar label, e.g. "Extrahieren"
  icon: ComponentType<{ className?: string }>; // import from lucide-react
  order: number; // bar position (Dateien=0 … Statistik=6)
  requiresFile: boolean; // true → gated behind a selected file
  Component: ComponentType; // the tab UI; reads useActiveFile() when requiresFile
}
