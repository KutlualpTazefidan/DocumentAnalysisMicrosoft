import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * React Query hooks for the Synthesise tab — admin LLM-driven question
 * generation per element. See
 * docs/superpowers/specs/2026-05-03-synthesise-ui-design.md.
 *
 * Endpoints:
 *   POST   /api/admin/docs/{slug}/synthesise (?box_id | ?page)
 *   GET    /api/admin/docs/{slug}/questions
 *   GET    /api/admin/docs/{slug}/questions/{box_id}
 *   PATCH  /api/admin/docs/{slug}/questions/{question_id}
 *   DELETE /api/admin/docs/{slug}/questions/{question_id}
 */

export interface Question {
  entry_id: string;
  text: string;
  box_id: string;
  /** LLM-generated reference answer; null until ⟨📝 Antworten⟩ runs. */
  answer?: string | null;
}

export type QuestionsByBox = Record<string, Question[]>;

export interface StreamEvent {
  event: "question" | "completed" | "done" | "cancelled" | "error";
  element_id?: string;
  entry_id?: string;
  text?: string;
  box_id?: string;
  accepted?: number;
  skipped_reason?: string | null;
  detail?: string;
}

async function fetchOk(url: string, init: RequestInit, token: string) {
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

export function useQuestions(slug: string, token: string) {
  return useQuery<QuestionsByBox>({
    queryKey: ["questions", slug],
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/questions`,
        { method: "GET" },
        token,
      );
      return r.json() as Promise<QuestionsByBox>;
    },
    retry: false,
  });
}

/** Edit a single answer. Empty text deletes the answer (sets the
 *  question's answer back to null). */
export function useEditAnswer(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { entryId: string; text: string }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/answers/${encodeURIComponent(params.entryId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: params.text }),
        },
        token,
      );
      return r.json() as Promise<{ entry_id: string; answer: string }>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", slug] });
    },
  });
}

/** Sync per-box answer generation. Backend reads the box's content +
 *  active questions, asks the LLM to answer each, and stores the
 *  results in the per-slug answers sidecar. The next /questions read
 *  surfaces them via the `answer` field. */
export function useAnswerBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (boxId: string) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/answer-box?box_id=${encodeURIComponent(boxId)}`,
        { method: "POST" },
        token,
      );
      return r.json() as Promise<{
        box_id: string;
        answered: number;
        skipped_reason: string | null;
      }>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", slug] });
    },
  });
}

/** Sync per-box generation. Returns the new questions (not the full list). */
export function useGenerateBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (boxId: string) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/synthesise?box_id=${encodeURIComponent(boxId)}`,
        { method: "POST" },
        token,
      );
      return r.json() as Promise<{
        box_id: string;
        questions: Question[];
        accepted: number;
        skipped_reason: string | null;
      }>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", slug] });
    },
  });
}

export function useRefineQuestion(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { questionId: string; text: string }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(params.questionId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: params.text }),
        },
        token,
      );
      return r.json() as Promise<{ new_entry_id: string }>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", slug] });
    },
  });
}

export function useDeprecateQuestion(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (questionId: string) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(questionId)}`,
        { method: "DELETE" },
        token,
      );
      return r.json() as Promise<{ event_id: string }>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", slug] });
    },
  });
}

/**
 * Streaming generation for page / full-doc scope. Returns an
 * AbortController so callers can cancel the in-flight request.
 *
 * The stream emits one NDJSON line per event. Events the caller cares
 * about: "question" (one accepted), "completed" (per element),
 * "cancelled", "error", and the terminal "done".
 */
export interface StreamHandles {
  controller: AbortController;
  done: Promise<void>;
}

export function streamGenerate(
  slug: string,
  token: string,
  scope: { page?: number },
  onEvent: (e: StreamEvent) => void,
): StreamHandles {
  const controller = new AbortController();
  const params = scope.page !== undefined ? `?page=${scope.page}` : "";
  const url = `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/synthesise${params}`;

  const done = (async () => {
    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "X-Auth-Token": token },
        signal: controller.signal,
      });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      onEvent({ event: "error", detail: (e as Error).message });
      return;
    }
    if (!response.ok || !response.body) {
      onEvent({ event: "error", detail: `${response.status} ${response.statusText}` });
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    try {
      while (true) {
        const { done: rDone, value } = await reader.read();
        if (rDone) break;
        buf += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            onEvent(JSON.parse(line) as StreamEvent);
          } catch {
            /* ignore malformed line */
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      onEvent({ event: "error", detail: (e as Error).message });
    }
  })();

  return { controller, done };
}
