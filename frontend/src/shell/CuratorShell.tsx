import { AnimatePresence, motion } from "framer-motion";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { CURATOR_THEME } from "./shared/ColorThemes";
import { RoleMenu } from "./shared/RoleMenu";
import { useToast } from "../shared/components/useToast";

export function CuratorShell() {
  const { role, name, tenantSlug, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { info } = useToast();
  // Cookie-mode logins have token=='' — gate on role only.
  if (role !== "curator") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header
        className="px-6 py-3 flex items-center justify-between flex-shrink-0"
        style={{ background: CURATOR_THEME.chrome, color: CURATOR_THEME.chromeFg }}
      >
        <nav className="flex items-center gap-4 text-sm">
          <Link to="/curate" className="font-semibold">Goldens — Kurator</Link>
          <Link to="/curate">Meine Dokumente</Link>
        </nav>
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
            theme={CURATOR_THEME}
            name={name ?? "curator"}
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
