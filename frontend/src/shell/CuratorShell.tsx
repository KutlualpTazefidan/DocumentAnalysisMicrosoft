import { AnimatePresence, motion } from "framer-motion";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { CURATOR_THEME } from "./shared/ColorThemes";
import { BamHeader } from "./BamHeader";
import { IconRail, type RailItem } from "./IconRail";
import { useToast } from "../shared/components/useToast";
import { Inbox } from "../shared/icons";

const CURATOR_NAV: RailItem[] = [
  { to: "/curate", match: "/curate", label: "Meine Dokumente", icon: Inbox },
];

export function CuratorShell() {
  const { role, name, tenantName, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { info } = useToast();
  // Cookie-mode logins have token=='' — gate on role only.
  if (role !== "curator") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  function handleLogout() { logout(); navigate("/login", { replace: true }); }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-canvas">
      <BamHeader
        theme={CURATOR_THEME}
        name={name ?? "curator"}
        tenantName={tenantName}
        onSettings={() => info("Einstellungen folgen in Kürze.")}
        onLogout={handleLogout}
      />
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <IconRail items={CURATOR_NAV} />
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
