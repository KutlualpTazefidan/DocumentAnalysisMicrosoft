import { AnimatePresence, motion } from "framer-motion";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { ADMIN_THEME } from "./shared/ColorThemes";
import { RoleBadge } from "./shared/RoleBadge";
import { Inbox, Users, Cpu, BarChart3, LogOut } from "../shared/icons";

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
          <Link to="/admin/inbox" className="flex items-center gap-1"><Inbox className="w-4 h-4" />Inbox</Link>
          <Link to="/admin/curators" className="flex items-center gap-1"><Users className="w-4 h-4" />Curators</Link>
          <Link to="/admin/pipelines" className="flex items-center gap-1"><Cpu className="w-4 h-4" />Pipelines</Link>
          <Link to="/admin/dashboard" className="flex items-center gap-1"><BarChart3 className="w-4 h-4" />Dashboard</Link>
        </nav>
        <div className="flex items-center gap-3">
          <RoleBadge theme={ADMIN_THEME} name={name ?? "admin"} />
          <button onClick={handleLogout} className="flex items-center gap-1 text-sm underline"><LogOut className="w-4 h-4" />Logout</button>
        </div>
      </header>
      <main className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            data-shell-motion
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
