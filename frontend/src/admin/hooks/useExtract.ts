import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exportSourceElements, extractRegion, getHtml, putHtml } from "../api/docs";
import { apiBase } from "../api/adminClient";
import { readNdjsonLines } from "../api/ndjson";
import type { WorkerEvent } from "../types/domain";

/** One assignment-time diagnostic emitted by the backend worker. */
export interface ExtractDiagnostic {
  page: number;
  kind:
    | "split"
    | "no_decomposition"
    | "caption_rescue"
    | "caption_rescue_failed";
  // Fields populated for "split" / "no_decomposition":
  block_bbox?: number[];
  block_type?: string;
  user_bboxes?: string[];
  n_sub_elements?: number;
  text_preview?: string;
  // Fields populated for "caption_rescue" / "caption_rescue_failed":
  source_bbox?: string;          // empty heading/caption user-bbox id
  target_visual_bbox?: string;   // table/figure user-bbox the caption was inside
  caption_text?: string;         // extracted caption (empty for failed)
  click_remap?: boolean;         // whether <caption data-source-box=...> was injected
  /** First ~400 chars of the visual element's HTML — populated for
   *  caption_rescue_failed so we can see what shape MinerU produced
   *  (helps diagnose where the caption text actually lives). */
  target_html_preview?: string;
}

/** Shape returned by GET /api/admin/docs/{slug}/mineru */
export interface MineruFile {
  elements: Array<{ box_id: string; html_snippet: string }>;
  diagnostics?: ExtractDiagnostic[];
}

async function getMineru(slug: string, token: string): Promise<MineruFile | null> {
  const r = await fetch(`${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/mineru`, {
    headers: { "X-Auth-Token": token },
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GET /mineru failed: ${r.status}`);
  return r.json() as Promise<MineruFile>;
}

export function useMineru(slug: string, token: string) {
  return useQuery({
    queryKey: ["mineru", slug],
    queryFn: () => getMineru(slug, token),
  });
}

export function useHtml(slug: string, token: string) {
  return useQuery({ queryKey: ["html", slug], queryFn: () => getHtml(slug, token) });
}

export function usePutHtml(slug: string, token: string) {
  return useMutation({ mutationFn: (html: string) => putHtml(slug, html, token) });
}

export function useExportSourceElements(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => exportSourceElements(slug, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}

export function useExtractRegion(slug: string, token: string) {
  return useMutation({ mutationFn: (boxId: string) => extractRegion(slug, boxId, token) });
}

export async function* streamSegment(
  slug: string,
  token: string,
  start?: number,
  end?: number,
): AsyncGenerator<WorkerEvent> {
  const params = new URLSearchParams();
  if (start !== undefined) params.set("start", String(start));
  if (end !== undefined) params.set("end", String(end));
  const qs = params.toString() ? `?${params.toString()}` : "";
  const r = await fetch(
    `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/segment${qs}`,
    {
      method: "POST",
      headers: { "X-Auth-Token": token },
    },
  );
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<WorkerEvent>(r.body);
}

export async function* streamExtract(slug: string, token: string, page?: number): AsyncGenerator<WorkerEvent> {
  const qs = page !== undefined ? `?page=${page}` : "";
  const r = await fetch(`${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/extract${qs}`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<WorkerEvent>(r.body);
}
