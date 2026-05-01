const BASE = (import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8001") as string;

export interface CheckTokenResponse { role: "admin" | "curator"; name: string; }

export async function checkToken(token: string): Promise<CheckTokenResponse> {
  const r = await fetch(`${BASE}/api/auth/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (r.status === 401) throw Object.assign(new Error("invalid"), { status: 401 });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
