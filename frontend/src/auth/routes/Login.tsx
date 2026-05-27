import { useSearchParams } from "react-router-dom";
import { LoginForm } from "../LoginForm";

/**
 * Standalone /login page — used for direct visits and the session-
 * expired redirect from the auth middleware. The landing-page entry
 * (most users hit it from there) opens the same form in a modal; see
 * landing/LoginModal.tsx.
 */
export function Login() {
  const [params] = useSearchParams();
  const reason = params.get("reason");
  // ?legacy=1 surfaces the API-Token tab for power users; first-time
  // visitors via Anmelden see only the credential flow.
  const legacyVisible = params.get("legacy") === "1";

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm bg-white rounded-lg shadow p-8 space-y-4">
        <h1 className="text-xl font-semibold">Anmeldung</h1>
        {reason === "expired" && (
          <p className="text-sm text-slate-600">
            Sitzung abgelaufen. Bitte erneut anmelden.
          </p>
        )}
        <LoginForm legacyVisible={legacyVisible} />
      </div>
    </div>
  );
}
