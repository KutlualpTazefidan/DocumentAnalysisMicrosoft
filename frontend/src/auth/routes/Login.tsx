import { useSearchParams } from "react-router-dom";
import { LoginForm } from "../LoginForm";

/**
 * Standalone /login page — used for direct visits and the session-
 * expired redirect from the auth middleware. The landing-page entry
 * (most users hit it from there) opens the same form in a modal; see
 * landing/LoginModal.tsx.
 *
 * BAM login: centered white card on a near-black backdrop, logo + GOLDENS
 * lockup, with the test-environment warning beneath — mirrors the BAM
 * reference login screen.
 */
export function Login() {
  const [params] = useSearchParams();
  const reason = params.get("reason");
  // ?legacy=1 surfaces the API-Token tab for power users; first-time
  // visitors via Anmelden see only the credential flow.
  const legacyVisible = params.get("legacy") === "1";

  return (
    <div className="min-h-screen flex items-center justify-center bg-backdrop p-4">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-lg shadow-xl p-8 space-y-5">
          <div className="flex flex-col items-center gap-3">
            <img src="/brand/bam-logo.png" alt="BAM" className="h-10 w-auto" />
            <h1 className="text-lg font-bold uppercase tracking-[0.18em] text-bam-navy">
              Goldens
            </h1>
          </div>
          {reason === "expired" && (
            <p className="text-sm text-ink-muted text-center">
              Sitzung abgelaufen. Bitte erneut anmelden.
            </p>
          )}
          <LoginForm legacyVisible={legacyVisible} />
        </div>
        <div className="mt-3 rounded bg-[#fff8e1] border-l-4 border-[#ffcb46] text-ink text-xs p-3">
          <strong>Achtung</strong> — Test- und Entwicklungsumgebung. Bitte keine
          produktiven Daten speichern.
        </div>
      </div>
    </div>
  );
}
