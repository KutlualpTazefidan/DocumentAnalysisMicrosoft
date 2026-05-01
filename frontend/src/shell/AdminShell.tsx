import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { ADMIN_THEME } from "./shared/ColorThemes";
import { RoleBadge } from "./shared/RoleBadge";

export function AdminShell() {
  const { token, role, name, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  if (!token || role !== "admin") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="min-h-screen flex flex-col">
      <header
        className="px-6 py-3 flex items-center justify-between"
        style={{ background: ADMIN_THEME.chrome, color: ADMIN_THEME.chromeFg }}
      >
        <nav className="flex items-center gap-4 text-sm">
          <Link to="/admin/inbox" className="font-semibold">Goldens</Link>
          <Link to="/admin/inbox">Inbox</Link>
          <Link to="/admin/curators">Curators</Link>
          <Link to="/admin/pipelines">Pipelines</Link>
          <Link to="/admin/dashboard">Dashboard</Link>
        </nav>
        <div className="flex items-center gap-3">
          <RoleBadge theme={ADMIN_THEME} name={name ?? "admin"} />
          <button onClick={handleLogout} className="text-sm underline">Logout</button>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
