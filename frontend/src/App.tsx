import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { TopBar } from "./components/TopBar";
import { Login } from "./routes/login";
import { DocsIndex } from "./routes/docs-index";
import { DocElements } from "./routes/doc-elements";
import { DocSynthesise } from "./routes/doc-synthesise";
import { ExtractRoute } from "./admin/routes/extract";
import { InboxRoute } from "./admin/routes/inbox";
import { SegmentRoute } from "./admin/routes/segment";

function RequireAuth() {
  const { token } = useAuth();
  const location = useLocation();
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return (
    <>
      <TopBar />
      <Outlet />
    </>
  );
}

export function App() {
  const { token } = useAuth();

  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to="/docs" replace />} />
          <Route path="/docs" element={<DocsIndex />} />
          <Route
            path="/docs/:slug/elements"
            element={<DocElements />}
          />
          <Route
            path="/docs/:slug/elements/:elementId"
            element={<DocElements />}
          />
          <Route
            path="/docs/:slug/synthesise"
            element={<DocSynthesise />}
          />
          <Route path="/local-pdf/inbox" element={<InboxRoute token={token!} />} />
          <Route path="/local-pdf/doc/:slug/segment" element={<SegmentRoute token={token!} />} />
          <Route path="/local-pdf/doc/:slug/extract" element={<ExtractRoute token={token!} />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
