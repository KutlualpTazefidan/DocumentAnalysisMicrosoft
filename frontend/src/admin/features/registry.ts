import type { TabDescriptor } from "./types";

// Auto-discover every admin/features/<key>/tab.tsx default export. Adding a tab
// = drop a folder; no shared file is edited. eager:true so the list is
// available synchronously for route + bar construction.
const modules = import.meta.glob("./*/tab.tsx", { eager: true });

export const WORKSPACE_TABS: TabDescriptor[] = Object.values(modules)
  .map((m) => (m as { default: TabDescriptor }).default)
  .sort((a, b) => a.order - b.order);
