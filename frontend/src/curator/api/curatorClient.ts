import type { DocMeta, DocumentElement } from "../../shared/types/domain";
import { apiFetch as adminApiFetch } from "../../admin/api/adminClient";
import { streamNdjson } from "./ndjson";
import type { SynthLine, SynthesiseRequest } from "../../shared/types/domain";

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

export async function listAssignedDocs(token: string): Promise<DocMeta[]> {
  const r = await adminApiFetch("/api/curate/docs", token);
  return r.json();
}

export async function listCurateElements(slug: string, token: string): Promise<DocumentElement[]> {
  const r = await adminApiFetch(`/api/curate/docs/${encodeURIComponent(slug)}/elements`, token);
  return r.json();
}

export interface PostQuestionBody { element_id: string; query: string; }
export interface PostedQuestion {
  question_id: string; element_id: string; curator_id: string;
  query: string; created_at: string;
}

export async function postQuestion(
  slug: string, body: PostQuestionBody, token: string,
): Promise<PostedQuestion> {
  const r = await adminApiFetch(`/api/curate/docs/${encodeURIComponent(slug)}/questions`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

// ---------------------------------------------------------------------------
// New curate endpoints — no explicit token; apiFetch reads from sessionStorage
// ---------------------------------------------------------------------------

export interface CuratorQuestion {
  question_id: string;
  element_id: string;
  curator_id: string;
  query: string;
  refined_query: string | null;
  deprecated: boolean;
  deprecated_reason: string | null;
  created_at: string;
}

export async function getCurateElement(
  slug: string,
  elementId: string,
): Promise<DocumentElement> {
  return apiFetch<DocumentElement>(
    `/api/curate/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elementId)}`,
  );
}

export async function listQuestions(
  slug: string,
  elementId?: string,
): Promise<CuratorQuestion[]> {
  const qs = elementId ? `?element_id=${encodeURIComponent(elementId)}` : "";
  return apiFetch<CuratorQuestion[]>(
    `/api/curate/docs/${encodeURIComponent(slug)}/questions${qs}`,
  );
}

export interface RefineQuestionBody { query: string; }

export async function refineQuestion(
  slug: string,
  questionId: string,
  body: RefineQuestionBody,
): Promise<CuratorQuestion> {
  return apiFetch<CuratorQuestion>(
    `/api/curate/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(questionId)}/refine`,
    { method: "POST", body },
  );
}

export interface DeprecateQuestionBody { reason?: string | null; }

export async function deprecateQuestion(
  slug: string,
  questionId: string,
  body: DeprecateQuestionBody,
): Promise<CuratorQuestion> {
  return apiFetch<CuratorQuestion>(
    `/api/curate/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(questionId)}/deprecate`,
    { method: "POST", body },
  );
}

// ---------------------------------------------------------------------------
// Synthesise streaming (from legacy docs.ts, kept for useSynthesise hook)
// ---------------------------------------------------------------------------

export async function streamSynthesise(
  slug: string,
  body: SynthesiseRequest,
  signal?: AbortSignal,
): Promise<AsyncIterable<SynthLine>> {
  const response = await rawFetch(
    `/api/docs/${encodeURIComponent(slug)}/synthesise`,
    { method: "POST", body, signal },
  );
  return streamNdjson<SynthLine>(response);
}
