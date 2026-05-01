import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../curator/api/curatorClient";
import { useAuth } from "../hooks/useAuth";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [token, setTokenInput] = useState("");
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
      // Pre-store so apiFetch reads it; if validation fails, clearToken runs.
      sessionStorage.setItem("goldens.api_token", token);
      await apiFetch("/api/health");
      login(token);
      navigate("/docs", { replace: true });
    } catch (err) {
      sessionStorage.removeItem("goldens.api_token");
      if (err instanceof ApiError && err.status === 401) {
        setError("Token wurde abgelehnt.");
      } else {
        setError("Server nicht erreichbar.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white rounded-lg shadow p-8 space-y-4"
      >
        <h1 className="text-xl font-semibold">Goldens — Anmeldung</h1>
        {reason === "expired" ? (
          <p className="text-sm text-slate-600">
            Sitzung abgelaufen. Bitte erneut Token eingeben.
          </p>
        ) : null}
        <label className="block">
          <span className="text-sm text-slate-700">API-Token</span>
          <input
            className="input mt-1"
            type="password"
            value={token}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="aus Terminal: $GOLDENS_API_TOKEN"
            autoFocus
            aria-label="API-Token"
          />
        </label>
        {error ? (
          <div role="alert" className="text-sm text-red-600">
            {error}
          </div>
        ) : null}
        <button
          type="submit"
          className="btn-primary w-full"
          disabled={submitting || !token.trim()}
        >
          {submitting ? "Prüfe…" : "Einloggen"}
        </button>
      </form>
    </div>
  );
}
