import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { Login } from "./routes/login";

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
          <Route path="/docs" element={<DocsIndexPlaceholder />} />
          <Route
            path="/docs/:slug/elements"
            element={<DocElementsPlaceholder />}
          />
          <Route
            path="/docs/:slug/elements/:elementId"
            element={<DocElementsPlaceholder />}
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

function DocsIndexPlaceholder() {
  return <div className="p-8">Docs Index (Task 11)</div>;
}
function DocElementsPlaceholder() {
  return <div className="p-8">Doc Elements (Task 23)</div>;
}
function SynthesisePlaceholder() {
  return <div className="p-8">Synthesise (Task 26)</div>;
}
function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
