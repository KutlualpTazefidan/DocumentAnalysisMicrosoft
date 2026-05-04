import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * React Query hooks for the Vergleich tab.
 *
 * Endpoints:
 *   GET  /api/admin/docs/{slug}/questions/{entry_id}/similar
 *   GET  /api/admin/pipelines
 *   POST /api/admin/pipelines/{name}/ask
 *   POST /api/admin/compare
 */

export interface SimilarHit {
  entry_id: string;
  text: string;
  box_id: string;
  chunk: string;
  bm25_score: number;
  cosine_score: number;
}

export interface SimilarResponse {
  entry_id: string;
  embedder: boolean;
  hits: SimilarHit[];
}

export interface PipelineInfo {
  name: string;
  label: string;
  available: boolean;
  note: string | null;
}

export interface PipelineChunk {
  chunk_id: string;
  title: string | null;
  chunk: string;
  score: number;
  source_file: string | null;
}

export interface AskResponse {
  pipeline: string;
  question: string;
  chunks: PipelineChunk[];
  answer: string;
}

export interface CompareResponse {
  bm25: number;
  cosine: number;
  embedder: boolean;
}

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

export function useSimilarQuestions(slug: string, token: string, entryId: string | null, k = 5) {
  return useQuery<SimilarResponse>({
    queryKey: ["similar", slug, entryId, k],
    enabled: !!slug && !!entryId,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(
          entryId!,
        )}/similar?k=${k}`,
        { method: "GET" },
        token,
      );
      return r.json() as Promise<SimilarResponse>;
    },
    retry: false,
  });
}

export function usePipelines(token: string) {
  return useQuery<PipelineInfo[]>({
    queryKey: ["pipelines"],
    queryFn: async () => {
      const r = await fetchOk(`${apiBase()}/api/admin/pipelines`, { method: "GET" }, token);
      return r.json() as Promise<PipelineInfo[]>;
    },
    retry: false,
  });
}

export interface SearchResponse {
  pipeline: string;
  question: string;
  chunks: PipelineChunk[];
}

export interface AnswerResponse {
  pipeline: string;
  question: string;
  answer: string;
}

/** Step 1 of the two-step Vergleich flow: just retrieve chunks. */
export function useSearchPipeline(token: string) {
  return useMutation({
    mutationFn: async (params: {
      name: string;
      question: string;
      topK?: number;
      source?: string;
    }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/${encodeURIComponent(params.name)}/search`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: params.question,
            top_k: params.topK ?? 5,
            source: params.source ?? null,
          }),
        },
        token,
      );
      return r.json() as Promise<SearchResponse>;
    },
  });
}

/** Step 2: answer using the chunks the user reviewed in step 1. */
export function useAnswerPipeline(token: string) {
  return useMutation({
    mutationFn: async (params: {
      name: string;
      question: string;
      chunks: PipelineChunk[];
    }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/${encodeURIComponent(params.name)}/answer`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: params.question, chunks: params.chunks }),
        },
        token,
      );
      return r.json() as Promise<AnswerResponse>;
    },
  });
}

export function useAskPipeline(token: string) {
  return useMutation({
    mutationFn: async (params: {
      name: string;
      question: string;
      topK?: number;
      source?: string;
    }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/${encodeURIComponent(params.name)}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: params.question,
            top_k: params.topK ?? 5,
            source: params.source ?? null,
          }),
        },
        token,
      );
      return r.json() as Promise<AskResponse>;
    },
  });
}

export function useCompareAnswers(token: string) {
  return useMutation({
    mutationFn: async (params: { reference: string; candidate: string }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/compare`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        },
        token,
      );
      return r.json() as Promise<CompareResponse>;
    },
  });
}

// ── Microsoft knowledge sources ────────────────────────────────────────────

export interface KnowledgeSource {
  slug: string;
  filename: string;
  pages: number;
  state: "uploaded" | "analyzed" | "chunked" | "embedded" | "indexed" | "error";
  error: string | null;
  index_name: string | null;
  external?: boolean;
}

export function useMicrosoftSources(token: string) {
  return useQuery<KnowledgeSource[]>({
    queryKey: ["microsoft-sources"],
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/microsoft/sources`,
        { method: "GET" },
        token,
      );
      return r.json() as Promise<KnowledgeSource[]>;
    },
    retry: false,
  });
}

/** Pings Azure AI Search for any kb-* indexes we don't have locally
 *  and adopts them. Returns the merged list. */
export function useRefreshMicrosoftSources(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/microsoft/sources/_refresh`,
        { method: "POST" },
        token,
      );
      return r.json() as Promise<KnowledgeSource[]>;
    },
    onSuccess: (data) =>
      qc.setQueryData<KnowledgeSource[]>(["microsoft-sources"], data),
  });
}

export function useUploadMicrosoftSource(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetchOk(
        `${apiBase()}/api/admin/pipelines/microsoft/sources`,
        { method: "POST", body: fd },
        token,
      );
      return r.json() as Promise<KnowledgeSource>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["microsoft-sources"] }),
  });
}

export function useDeleteMicrosoftSource(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (slug: string) => {
      await fetchOk(
        `${apiBase()}/api/admin/pipelines/microsoft/sources/${encodeURIComponent(slug)}`,
        { method: "DELETE" },
        token,
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["microsoft-sources"] }),
  });
}
