import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { Login } from "./routes/login";
import { DocsIndex } from "./routes/docs-index";
import { DocElements } from "./routes/doc-elements";

function RequireAuth() {
  const { token } = useAuth();
  const location = useLocation();
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <Outlet />;
}

export function App() {
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
            element={<SynthesisePlaceholder />}
          />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function SynthesisePlaceholder() {
  return <div className="p-8">Synthesise (Task 26)</div>;
}
function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
