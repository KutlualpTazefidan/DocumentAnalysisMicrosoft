import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { CURATOR_THEME } from "./shared/ColorThemes";
import { RoleBadge } from "./shared/RoleBadge";

export function CuratorShell() {
  const { token, role, name, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  if (!token || role !== "curator") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="min-h-screen flex flex-col">
      <header
        className="px-6 py-3 flex items-center justify-between"
        style={{ background: CURATOR_THEME.chrome, color: CURATOR_THEME.chromeFg }}
      >
        <nav className="flex items-center gap-4 text-sm">
          <Link to="/curate" className="font-semibold">Goldens — Curator</Link>
          <Link to="/curate">My Docs</Link>
        </nav>
        <div className="flex items-center gap-3">
          <RoleBadge theme={CURATOR_THEME} name={name ?? "curator"} />
          <button onClick={handleLogout} className="text-sm underline">Logout</button>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
