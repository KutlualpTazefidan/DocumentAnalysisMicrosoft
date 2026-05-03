import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../useAuth";
import { checkToken } from "../api";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [params] = useSearchParams();
  const reason = params.get("reason");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const ident = await checkToken(token);
      login(token, ident.role, ident.name);
      navigate(ident.role === "admin" ? "/admin/inbox" : "/curate/", { replace: true });
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 401 ? "Token wurde abgelehnt." : "Server nicht erreichbar.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="w-full max-w-sm bg-white rounded-lg shadow p-8 space-y-4">
        <h1 className="text-xl font-semibold">Goldens — Anmeldung</h1>
        {reason === "expired" && (
          <p className="text-sm text-slate-600">Sitzung abgelaufen. Bitte erneut Token eingeben.</p>
        )}
        <label className="block">
          <span className="text-sm text-slate-700">API-Token</span>
          <input
            className="input mt-1"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="aus Terminal: $GOLDENS_API_TOKEN oder Curator-Token"
            autoFocus
            aria-label="API-Token"
          />
        </label>
        {error && <div role="alert" className="text-sm text-red-600">{error}</div>}
        <button type="submit" className="btn-primary w-full" disabled={submitting || !token.trim()}>
          {submitting ? "Prüfe…" : "Einloggen"}
        </button>
      </form>
    </div>
  );
}
