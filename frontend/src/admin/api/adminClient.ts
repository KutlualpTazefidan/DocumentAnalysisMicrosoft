const BASE = (import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8001") as string;

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
  return `${BASE}/api/admin`;
}
