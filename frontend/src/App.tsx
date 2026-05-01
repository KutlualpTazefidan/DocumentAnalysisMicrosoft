import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { Login } from "./auth/routes/Login";
import { AdminShell } from "./shell/AdminShell";
import { CuratorShell } from "./shell/CuratorShell";
import { Inbox } from "./admin/routes/inbox";
import { Segment } from "./admin/routes/segment";
import { Extract } from "./admin/routes/extract";
import { Synthesise } from "./admin/routes/Synthesise";
import { DocCurators } from "./admin/routes/DocCurators";
import { Curators } from "./admin/routes/Curators";
import { CuratorActivity } from "./admin/routes/CuratorActivity";
import { Pipelines } from "./admin/routes/Pipelines";
import { Dashboard } from "./admin/routes/Dashboard";
import { CuratorDocs } from "./curator/routes/Docs";
import { CuratorDocPage } from "./curator/routes/DocPage";

export function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<Navigate to="inbox" replace />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="doc/:slug/segment" element={<Segment />} />
          <Route path="doc/:slug/extract" element={<Extract />} />
          <Route path="doc/:slug/synthesise" element={<Synthesise />} />
          <Route path="doc/:slug/curators" element={<DocCurators />} />
          <Route path="curators" element={<Curators />} />
          <Route path="curators/:id/activity" element={<CuratorActivity />} />
          <Route path="pipelines" element={<Pipelines />} />
          <Route path="dashboard" element={<Dashboard />} />
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
        <Route path="/local-pdf/doc/:slug/segment" element={<RedirectWithSlug to="/admin/doc/:slug/segment" />} />
        <Route path="/local-pdf/doc/:slug/extract" element={<RedirectWithSlug to="/admin/doc/:slug/extract" />} />
        <Route path="/docs" element={<Navigate to="/admin/inbox" replace />} />
        <Route path="/docs/:slug/elements" element={<RedirectWithSlug to="/admin/doc/:slug/segment" />} />
        <Route path="/docs/:slug/elements/:elementId" element={<RedirectWithSlug to="/admin/doc/:slug/segment" />} />
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
