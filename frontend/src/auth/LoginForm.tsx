import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./useAuth";
import { checkToken, loginWithCredentials } from "./api";
import { Building2, User, Lock, Eye, EyeOff } from "../shared/icons";

type Mode = "credentials" | "token";

const LAST_TENANT_KEY = "lpdf.lastTenantSlug";

interface Props {
  /** Render the legacy API-token tab. /login passes ``?legacy=1`` →
   *  true; the landing-modal never shows it. */
  legacyVisible?: boolean;
  /** Called when login succeeds AFTER the auth context is updated and
   *  navigation is queued. Modal hosts use this to close themselves. */
  onSuccess?: () => void;
}

/**
 * The auth form body — used by both the standalone /login page and the
 * landing-page Anmeldung modal. Owns its own submit + validation state;
 * routing happens here so the post-login flow is identical regardless
 * of where the form is rendered.
 */
export function LoginForm({ legacyVisible = false, onSuccess }: Props): JSX.Element {
  const navigate = useNavigate();
  const { login } = useAuth();
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

  const [showPw, setShowPw] = useState(false);

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
      // No token to keep — cookie carries identity. Pass empty string
      // into login() so existing hooks that read `token` see "" (and
      // skip the X-Auth-Token header thanks to the adminClient guard).
      login(
        "",
        ident.role as "admin" | "curator",
        ident.pseudonym,
        ident.tenant_slug,
        ident.tenant_name,
      );
      localStorage.setItem(LAST_TENANT_KEY, tenantSlug.trim());
      onSuccess?.();
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
        setError("Login fehlgeschlagen — Fachbereich, Benutzername oder Passwort falsch.");
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
      onSuccess?.();
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
    <div className="space-y-4">
      {legacyVisible && (
        <div className="flex gap-2 border-b border-slate-200">
          <button
            type="button"
            onClick={() => {
              setMode("credentials");
              setError(null);
            }}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              mode === "credentials"
                ? "border-brand-500 text-brand-700"
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
                ? "border-brand-500 text-brand-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            API-Token (alt)
          </button>
        </div>
      )}

      {mode === "credentials" ? (
        <form onSubmit={handleCredentialsSubmit} className="space-y-3">
          <label className="block">
            <span className="text-sm text-ink">Fachbereich</span>
            <div className="relative mt-1">
              <Building2 className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" aria-hidden />
              <input
                className="input pl-9"
                type="text"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
                placeholder="z.B. default"
                autoComplete="organization"
                aria-label="Fachbereich"
              />
            </div>
            <span className="text-xs text-ink-muted mt-1 block">
              Leer lassen oder „default", falls dir niemand etwas anderes gesagt hat.
            </span>
          </label>
          <label className="block">
            <span className="text-sm text-ink">Benutzername</span>
            <div className="relative mt-1">
              <User className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" aria-hidden />
              <input
                className="input pl-9"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                aria-label="Benutzername"
              />
            </div>
          </label>
          <label className="block">
            <span className="text-sm text-ink">Passwort</span>
            <div className="relative mt-1">
              <Lock className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" aria-hidden />
              <input
                className="input pl-9 pr-9"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                aria-label="Passwort"
              />
              <button
                type="button"
                onClick={() => setShowPw((s) => !s)}
                aria-label={showPw ? "Passwort verbergen" : "Passwort anzeigen"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-ink-muted hover:text-bam-navy"
              >
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </label>
          {error && (
            <div role="alert" className="text-sm text-red-600">
              {error}
            </div>
          )}
          <p className="text-xs text-slate-500">
            Im Audit-Log erscheint dein Pseudonym, nie dein Benutzername.
          </p>
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
  );
}
