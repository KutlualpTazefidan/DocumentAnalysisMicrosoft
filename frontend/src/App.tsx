import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { Landing } from "./landing/Landing";
import { Login } from "./auth/routes/Login";
import { AdminShell } from "./shell/AdminShell";
import { CuratorShell } from "./shell/CuratorShell";
import { Synthesise } from "./admin/routes/Synthesise";
import { Comparison } from "./admin/routes/Comparison";
import { Provenienz } from "./admin/routes/Provenienz";
import { Agent } from "./admin/routes/Agent";
import { Knowledge } from "./admin/routes/Knowledge";
import { DocCurators } from "./admin/routes/DocCurators";
import { WorkspaceLayout } from "./admin/components/WorkspaceLayout";
import { TabRoute } from "./admin/components/TabRoute";
import { WORKSPACE_TABS } from "./admin/features/registry";
import { Curators } from "./admin/routes/Curators";
import { CuratorActivity } from "./admin/routes/CuratorActivity";
import { Pipelines } from "./admin/routes/Pipelines";
import { Dashboard } from "./admin/routes/Dashboard";
import { TenantsAdmin } from "./admin/routes/TenantsAdmin";
import { Settings } from "./admin/routes/Settings";
import { CuratorDocs } from "./curator/routes/Docs";
import { CuratorDocPage } from "./curator/routes/DocPage";

export function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<Navigate to="files" replace />} />

          {/* Workspace: registry-driven top-level tabs (Dateien, Statistik, …). */}
          <Route element={<WorkspaceLayout />}>
            {WORKSPACE_TABS.map((d) => (
              <Route key={d.key} path={d.key} element={<TabRoute descriptor={d} />} />
            ))}
          </Route>

          {/* Bridges for converted tabs. */}
          <Route path="inbox" element={<Navigate to="/admin/files" replace />} />
          <Route path="doc/:slug/statistics" element={<RedirectWithSlug to="/admin/statistics?file=:slug" />} />

          {/* Segment route was merged into extract — redirect any legacy
              navigation to extract so old bookmarks still resolve. */}
          <Route path="doc/:slug/segment" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
          <Route path="doc/:slug/extract" element={<RedirectWithSlug to="/admin/extract?file=:slug" />} />
          <Route path="doc/:slug/synthesise" element={<Synthesise />} />
          <Route path="doc/:slug/compare" element={<Comparison />} />
          <Route path="doc/:slug/provenienz" element={<Provenienz />} />
          <Route path="doc/:slug/agent" element={<Agent />} />
          <Route path="doc/:slug/curators" element={<DocCurators />} />
          <Route path="curators" element={<Curators />} />
          <Route path="curators/:id/activity" element={<CuratorActivity />} />
          <Route path="pipelines" element={<Pipelines />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="tenants" element={<TenantsAdmin />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="/curate" element={<CuratorShell />}>
          <Route index element={<CuratorDocs />} />
          <Route path="doc/:slug" element={<CuratorDocPage />} />
          <Route path="doc/:slug/element/:elementId" element={<CuratorDocPage />} />
        </Route>

        {/* Legacy URL redirects — keep old bookmarks working after the
            coherence-and-roles migration. Pre-A.1.0 the SPA had a split
            tree (/local-pdf/* and /docs/*); these now redirect to the
            role-prefixed equivalents. */}
        <Route path="/local-pdf/inbox" element={<Navigate to="/admin/inbox" replace />} />
        <Route path="/local-pdf/doc/:slug/segment" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
        <Route path="/local-pdf/doc/:slug/extract" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
        <Route path="/docs" element={<Navigate to="/admin/inbox" replace />} />
        <Route path="/docs/:slug/elements" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
        <Route path="/docs/:slug/elements/:elementId" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
        <Route path="/docs/:slug/synthesise" element={<RedirectWithSlug to="/admin/doc/:slug/synthesise" />} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function RedirectWithSlug({ to }: { to: string }): JSX.Element {
  const params = useParams();
  let target = to;
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) target = target.replace(`:${k}`, v);
  }
  return <Navigate to={target} replace />;
}

function NotFound() {
  return (
    <div className="p-8 max-w-md mx-auto text-center">
      <h1 className="text-2xl font-semibold mb-2">Page not found</h1>
      <a href="/login" className="text-blue-600 underline">Go home</a>
    </div>
  );
}
