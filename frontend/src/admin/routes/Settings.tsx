import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Info } from "lucide-react";
import { useAuth } from "../../auth/useAuth";
import { T } from "../styles/typography";

export function Settings(): JSX.Element {
  const { role, name, tenantSlug, logout } = useAuth();
  const navigate = useNavigate();
  const roleLabel =
    role === "admin" ? "Administrator" : role === "curator" ? "Kurator" : "—";

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-2xl">
        <h1 className={`${T.cardTitle} mb-1`}>Einstellungen</h1>
        <p className={`${T.cardSubtle} mb-5`}>Dein Konto in diesem Fachbereich.</p>

        <section className="card overflow-hidden">
          <h2 className={`px-4 py-2.5 border-b border-line bam-title`}>
            Konto
          </h2>
          <Row label="Pseudonym">{name ?? "—"}</Row>
          <Row label="Rolle">
            <span className={`inline-block rounded-full bg-rowsel text-bam-cyan-700 px-2.5 py-0.5 font-medium ${T.body}`}>
              {roleLabel}
            </span>
          </Row>
          <Row label="Fachbereich">
            <span className={T.mono}>{tenantSlug ?? "—"}</span>
          </Row>
        </section>

        <div className="mt-4 card px-4 py-3 flex items-start gap-2.5">
          <Info className="w-4 h-4 text-ink-muted mt-0.5 shrink-0" aria-hidden />
          <p className={`${T.body} text-ink-muted`}>
            Benutzername und Passwort werden zentral von der Administration
            verwaltet und können hier nicht geändert werden.
          </p>
        </div>

        <div className="mt-6">
          <button type="button" className="btn-danger" onClick={handleLogout}>
            Abmelden
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-line last:border-b-0">
      <div className={`w-40 shrink-0 ${T.body} text-ink-muted`}>{label}</div>
      <div className={`${T.body} text-ink`}>{children}</div>
    </div>
  );
}
