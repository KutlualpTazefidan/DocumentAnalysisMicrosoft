import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * React Query hooks for the Provenienz tab.
 *
 * Endpoints:
 *   POST   /api/admin/provenienz/sessions
 *   GET    /api/admin/provenienz/sessions[?slug=...]
 *   GET    /api/admin/provenienz/sessions/{session_id}
 *   DELETE /api/admin/provenienz/sessions/{session_id}
 */

// ---- Types ----

export interface SessionMeta {
  session_id: string;
  slug: string;
  root_chunk_id: string;
  status: "open" | "closed";
  created_at: string;
  last_touched_at: string;
  pinned_approach_ids: string[];
}

export interface ProvNode {
  node_id: string;
  session_id: string;
  kind: string;
  payload: Record<string, unknown>;
  actor: string;
  created_at: string;
}

export interface ProvEdge {
  edge_id: string;
  session_id: string;
  from_node: string;
  to_node: string;
  kind: string;
  reason: string | null;
  actor: string;
  created_at: string;
}

export interface SessionDetail {
  meta: SessionMeta;
  nodes: ProvNode[];
  edges: ProvEdge[];
}

export interface CreateSessionRequest {
  slug: string;
  root_chunk_id: string;
}

// ---- fetchOk (shared util — duplicated from useComparison rather than refactored) ----

async function fetchOk(url: string, init: RequestInit, token: string): Promise<Response> {
  const r = await fetch(url, {
    ...init,
    headers: { ...(init.headers ?? {}), "X-Auth-Token": token },
  });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep status fallback */
    }
    throw new Error(detail);
  }
  return r;
}

// ---- Hooks ----

export function useSessions(slug: string, token: string) {
  return useQuery<SessionMeta[]>({
    queryKey: ["provenienz", "sessions", slug],
    enabled: !!slug && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions?slug=${encodeURIComponent(slug)}`,
        { method: "GET" },
        token,
      );
      const body = (await r.json()) as { sessions: SessionMeta[] };
      return body.sessions;
    },
  });
}

export function useSession(sessionId: string | null, token: string) {
  return useQuery<SessionDetail>({
    queryKey: ["provenienz", "session", sessionId],
    enabled: !!sessionId && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as SessionDetail;
    },
  });
}

export function useCreateSession(token: string) {
  const qc = useQueryClient();
  return useMutation<SessionMeta, Error, CreateSessionRequest>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      return (await r.json()) as SessionMeta;
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["provenienz", "sessions", created.slug] });
    },
  });
}

export function useDeleteSession(token: string, slug: string) {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: async (sessionId) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}`,
        { method: "DELETE" },
        token,
      );
      return (await r.json()) as { ok: boolean };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "sessions", slug] });
    },
  });
}
