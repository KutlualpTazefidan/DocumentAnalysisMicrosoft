import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../useAuth";
import { checkToken, loginWithCredentials } from "../api";

type Mode = "credentials" | "token";

const LAST_TENANT_KEY = "lpdf.lastTenantSlug";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [params] = useSearchParams();
  const reason = params.get("reason");
  const [mode, setMode] = useState<Mode>("credentials");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Credentials mode state.
  const [tenantSlug, setTenantSlug] = useState<string>(
    localStorage.getItem(LAST_TENANT_KEY) ?? "default",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // Token mode state (legacy).
  const [token, setToken] = useState("");

  async function handleCredentialsSubmit(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (!tenantSlug.trim() || !username.trim() || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      const ident = await loginWithCredentials(
        tenantSlug.trim(),
        username.trim(),
        password,
      );
      // No token to keep — cookie carries identity going forward.
      // Pass empty string into the legacy `login()` so existing
      // hooks that read `token` see "" (and skip the X-Auth-Token
      // header thanks to the adminClient guard).
      login(
        "",
        ident.role as "admin" | "curator",
        ident.pseudonym,
        ident.tenant_slug,
      );
      localStorage.setItem(LAST_TENANT_KEY, tenantSlug.trim());
      navigate(ident.role === "admin" ? "/admin/inbox" : "/curate/", {
        replace: true,
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      const lockedUntil = (err as { lockedUntil?: string }).lockedUntil;
      if (status === 429 && lockedUntil) {
        setError(
          `Zu viele Fehlversuche. Erneut möglich ab ${new Date(lockedUntil).toLocaleTimeString()}.`,
        );
      } else if (status === 401) {
        setError("Login fehlgeschlagen — Tenant, Username oder Passwort falsch.");
      } else {
        setError("Server nicht erreichbar.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTokenSubmit(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const ident = await checkToken(token);
      login(token, ident.role, ident.name);
      navigate(ident.role === "admin" ? "/admin/inbox" : "/curate/", {
        replace: true,
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 401 ? "Token wurde abgelehnt." : "Server nicht erreichbar.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm bg-white rounded-lg shadow p-8 space-y-4">
        <h1 className="text-xl font-semibold">Local-PDF — Anmeldung</h1>
        {reason === "expired" && (
          <p className="text-sm text-slate-600">
            Sitzung abgelaufen. Bitte erneut anmelden.
          </p>
        )}
        <div className="flex gap-2 border-b border-slate-200">
          <button
            type="button"
            onClick={() => {
              setMode("credentials");
              setError(null);
            }}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === "credentials"
                ? "border-blue-500 text-blue-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Benutzer
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("token");
              setError(null);
            }}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === "token"
                ? "border-blue-500 text-blue-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            API-Token (alt)
          </button>
        </div>

        {mode === "credentials" ? (
          <form onSubmit={handleCredentialsSubmit} className="space-y-3">
            <label className="block">
              <span className="text-sm text-slate-700">Tenant-Slug</span>
              <input
                className="input mt-1"
                type="text"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
                placeholder="z.B. default"
                autoComplete="organization"
                aria-label="Tenant-Slug"
              />
            </label>
            <label className="block">
              <span className="text-sm text-slate-700">Benutzername</span>
              <input
                className="input mt-1"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                aria-label="Benutzername"
              />
            </label>
            <label className="block">
              <span className="text-sm text-slate-700">Passwort</span>
              <input
                className="input mt-1"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                aria-label="Passwort"
              />
            </label>
            {error && (
              <div role="alert" className="text-sm text-red-600">
                {error}
              </div>
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={
                submitting ||
                !tenantSlug.trim() ||
                !username.trim() ||
                !password
              }
            >
              {submitting ? "Prüfe…" : "Einloggen"}
            </button>
            <p className="text-xs text-slate-500">
              Im Audit-Log erscheint dein Pseudonym, nie dein Benutzername.
            </p>
          </form>
        ) : (
          <form onSubmit={handleTokenSubmit} className="space-y-3">
            <label className="block">
              <span className="text-sm text-slate-700">API-Token</span>
              <input
                className="input mt-1"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="$GOLDENS_API_TOKEN oder Curator-Token"
                autoFocus
                aria-label="API-Token"
              />
            </label>
            {error && (
              <div role="alert" className="text-sm text-red-600">
                {error}
              </div>
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={submitting || !token.trim()}
            >
              {submitting ? "Prüfe…" : "Einloggen"}
            </button>
            <p className="text-xs text-slate-500">
              Legacy-Pfad — wird mit Phase 5 entfernt. Lieber den
              Benutzer-Tab nutzen.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
