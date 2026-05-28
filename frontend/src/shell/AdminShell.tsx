import { AnimatePresence, motion } from "framer-motion";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LlmTopBarControl } from "../admin/components/LlmTopBarControl";
import { useAuth } from "../auth/useAuth";
import { ADMIN_THEME } from "./shared/ColorThemes";
import { RoleMenu } from "./shared/RoleMenu";
import { useToast } from "../shared/components/useToast";
import { Inbox, Users, Cpu, BarChart3, Building2 } from "../shared/icons";

export function AdminShell() {
  const { token, role, name, tenantSlug, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { info } = useToast();
  // Cookie-mode logins land here with token=='' and role='admin' — we
  // gate on role only so the cookie flow works. Legacy token-mode still
  // sets both, so it's also fine.
  if (role !== "admin") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header
        className="px-6 py-3 flex items-center gap-4 flex-shrink-0"
        style={{ background: ADMIN_THEME.chrome, color: ADMIN_THEME.chromeFg }}
      >
        <nav className="flex items-center gap-4 text-sm">
          <Link to="/admin/inbox" className="font-semibold">Goldens</Link>
          <Link to="/admin/inbox" className="flex items-center gap-1"><Inbox className="w-4 h-4" />Posteingang</Link>
          <Link to="/admin/curators" className="flex items-center gap-1"><Users className="w-4 h-4" />Kuratoren</Link>
          <Link to="/admin/tenants" className="flex items-center gap-1"><Building2 className="w-4 h-4" />Fachbereiche</Link>
          <Link to="/admin/pipelines" className="flex items-center gap-1"><Cpu className="w-4 h-4" />Pipelines</Link>
          <Link to="/admin/dashboard" className="flex items-center gap-1"><BarChart3 className="w-4 h-4" />Übersicht</Link>
        </nav>
        {/* vLLM controls — centered in the available space between
            nav links and the user/logout cluster on the right. */}
        <div className="flex-1 flex justify-center">
          <LlmTopBarControl token={token ?? ""} />
        </div>
        <div className="flex items-center gap-3">
          {tenantSlug && (
            <span
              className="px-2 py-0.5 rounded text-xs font-mono border border-white/30"
              title="Aktiver Fachbereich"
            >
              {tenantSlug}
            </span>
          )}
          <RoleMenu
            theme={ADMIN_THEME}
            name={name ?? "admin"}
            onSettings={() => info("Einstellungen folgen in Kürze.")}
            onLogout={handleLogout}
          />
        </div>
      </header>
      <main className="flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            data-shell-motion
            className="h-full"
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
