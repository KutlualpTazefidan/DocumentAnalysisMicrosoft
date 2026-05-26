// Relative URL → calls go through the Vite dev-server proxy in dev (which
// forwards /api/* to the backend) and same-origin in prod (static-mount).
const BASE = (import.meta.env.VITE_API_BASE ?? "") as string;

export type Role = "admin" | "curator" | "reviewer";

/** Legacy token-introspect response. Still used by the API-token form. */
export interface CheckTokenResponse {
  role: "admin" | "curator";
  name: string;
}

/** Modern login response — driven by POST /api/auth/login. ``pseudonym``
 *  is the user-facing audit identity; ``name`` mirrors it for the
 *  existing useAuth surface (older code reads `name`). */
export interface IdentityResponse {
  role: Role;
  pseudonym: string;
  tenant_slug: string | null;
  name: string;
}

export async function checkToken(token: string): Promise<CheckTokenResponse> {
  const r = await fetch(`${BASE}/api/auth/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (r.status === 401)
    throw Object.assign(new Error("invalid"), { status: 401 });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/** Username + password login. Backend sets an HttpOnly cookie; browser
 *  attaches it to subsequent same-origin requests when fetch is called
 *  with credentials: 'include'. */
export async function loginWithCredentials(
  tenantSlug: string,
  username: string,
  password: string,
): Promise<IdentityResponse> {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      tenant_slug: tenantSlug,
      username,
      password,
    }),
  });
  if (r.status === 401)
    throw Object.assign(new Error("invalid credentials"), { status: 401 });
  if (r.status === 429) {
    // Rate-limited: surface the locked_until timestamp so the form can
    // show "try again at HH:MM".
    let lockedUntil = "";
    try {
      const body = await r.json();
      if (body?.detail?.locked_until) lockedUntil = body.detail.locked_until;
    } catch {
      /* ignore */
    }
    throw Object.assign(new Error("too many attempts"), {
      status: 429,
      lockedUntil,
    });
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/** Idempotent: revokes the current session (if any) and clears the
 *  cookie. Returns even when the user wasn't logged in. */
export async function logoutSession(): Promise<void> {
  await fetch(`${BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

/** Returns identity for the current session, or throws 401 when no
 *  session is active. Useful on page-refresh to restore identity state
 *  without re-prompting for credentials. */
export async function whoAmI(): Promise<IdentityResponse> {
  const r = await fetch(`${BASE}/api/auth/me`, {
    credentials: "include",
  });
  if (r.status === 401)
    throw Object.assign(new Error("not authenticated"), { status: 401 });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
