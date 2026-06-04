import { AnimatePresence, motion } from "framer-motion";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LlmTopBarControl } from "../admin/components/LlmTopBarControl";
import { useAuth } from "../auth/useAuth";
import { ADMIN_THEME } from "./shared/ColorThemes";
import { BamHeader } from "./BamHeader";
import { IconRail, type RailItem } from "./IconRail";
import { Inbox, Users, Cpu, BarChart3, Building2 } from "../shared/icons";

const ADMIN_NAV: RailItem[] = [
  { to: "/admin/inbox", match: "/admin/inbox", label: "Dokumente", icon: Inbox },
  { to: "/admin/curators", match: "/admin/curators", label: "Kuratoren", icon: Users },
  { to: "/admin/tenants", match: "/admin/tenants", label: "Fachbereiche", icon: Building2 },
  { to: "/admin/pipelines", match: "/admin/pipelines", label: "Pipelines", icon: Cpu },
  { to: "/admin/dashboard", match: "/admin/dashboard", label: "Übersicht", icon: BarChart3 },
];

export function AdminShell() {
  const { token, role, name, tenantSlug, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  // Cookie-mode logins land here with token=='' and role='admin' — we
  // gate on role only so the cookie flow works. Legacy token-mode still
  // sets both, so it's also fine.
  if (role !== "admin") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-canvas">
      <BamHeader
        theme={ADMIN_THEME}
        name={name ?? "admin"}
        tenantSlug={tenantSlug}
        onSettings={() => navigate("/admin/settings")}
        onLogout={handleLogout}
        centerSlot={<LlmTopBarControl token={token ?? ""} />}
      />
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <IconRail items={ADMIN_NAV} />
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
    </div>
  );
}
