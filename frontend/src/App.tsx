import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { TopBar } from "./components/TopBar";
import { Login } from "./routes/login";
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
