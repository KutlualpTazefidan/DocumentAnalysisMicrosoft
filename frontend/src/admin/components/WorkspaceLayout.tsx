// frontend/src/admin/components/WorkspaceLayout.tsx
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useDocs } from "../hooks/useDocs";
import { useActiveFile } from "../hooks/useActiveFile";
import { WORKSPACE_TABS } from "../features/registry";

/** The workspace shell: one tab bar (derived from the registry) + a global file
 * dropdown on the right, with the active tab below. Replaces the per-route
 * tab bars. */
export function WorkspaceLayout(): JSX.Element {
  const { pathname } = useLocation();
  const { token } = useAuth();
  const docs = useDocs(token ?? "");
  const { file, setFile } = useActiveFile();
  const query = file ? `?file=${encodeURIComponent(file)}` : "";

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-4 py-2 bg-white flex-shrink-0 border-b border-line">
        {WORKSPACE_TABS.map((t) => {
          const active = pathname.endsWith(`/${t.key}`);
          const Icon = t.icon;
          return (
            <Link
              key={t.key}
              to={`/admin/${t.key}${query}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm ${
                active ? "bg-cyan-50 text-bam-cyan" : "text-ink-muted hover:bg-slate-100"
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </Link>
          );
        })}
        <select
          aria-label="Aktive Datei"
          className="ml-auto rounded border border-slate-300 px-2 py-1 text-sm max-w-xs"
          value={file ?? ""}
          onChange={(e) => setFile(e.target.value || null)}
        >
          <option value="">— Datei wählen —</option>
          {(docs.data ?? []).map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.filename}
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
}
