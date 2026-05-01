const TOKEN_KEY = "goldens.api_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    public url: string,
  ) {
    super(typeof detail === "string" ? detail : `HTTP ${status} on ${url}`);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** When true, skips the X-Auth-Token header (e.g. for /api/health pre-auth check). */
  skipAuth?: boolean;
  /** When true, returns the Response object instead of parsed JSON (for streaming). */
  raw?: boolean;
}

export async function apiFetch<T = unknown>(
  url: string,
  opts: ApiOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (!opts.skipAuth) {
    const token = getToken();
    if (token) headers["X-Auth-Token"] = token;
  }
  const response = await fetch(url, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new Event("goldens:logout"));
    let detail: unknown = "unauthorized";
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* response body not json */
    }
    throw new ApiError(401, detail, url);
  }

  if (!response.ok) {
    let detail: unknown = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      /* response body not json */
    }
    throw new ApiError(response.status, detail, url);
  }

  if (opts.raw) {
    return response as unknown as T;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function rawFetch(
  url: string,
  opts: ApiOptions = {},
): Promise<Response> {
  return apiFetch<Response>(url, { ...opts, raw: true });
}
