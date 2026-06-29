import { useActiveFile } from "../hooks/useActiveFile";
import type { TabDescriptor } from "../features/types";

/** Shell-gated mount: a file-requiring tab shows a single empty state until a
 * file is selected, so each tab's body can assume a file is present. */
export function TabRoute({ descriptor }: { descriptor: TabDescriptor }): JSX.Element {
  const { file } = useActiveFile();
  const { Component, requiresFile } = descriptor;
  if (requiresFile && !file) {
    return (
      <div className="p-8 text-ink-muted text-sm">
        Bitte wählen Sie oben rechts eine Datei.
      </div>
    );
  }
  return <Component />;
}
