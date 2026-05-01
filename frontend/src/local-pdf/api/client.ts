// Default to a relative URL so calls go through the Vite dev-server proxy
// (configured in vite.config.ts to forward /api → backend) and, in production,
// hit whatever origin serves the frontend (Task 27's static-mount means the
// backend serves the SPA, so same-origin is correct). The env override is
// retained for tests and for split-host deployments.
const BASE = (import.meta.env.VITE_LOCAL_PDF_API_BASE ?? "") as string;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function authHeaders(token: string): HeadersInit {
  return { "X-Auth-Token": token };
}

export async function apiFetch(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  headers.set("X-Auth-Token", token);
  const resp = await fetch(`${BASE}${path}`, { ...init, headers });
  if (resp.status === 401) {
    window.dispatchEvent(new CustomEvent("local-pdf:401"));
    throw new ApiError(401, "unauthorized");
  }
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
  return resp;
}

export function apiBase(): string {
  return BASE;
}
