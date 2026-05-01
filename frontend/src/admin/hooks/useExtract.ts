import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exportSourceElements, extractRegion, getHtml, putHtml } from "../api/docs";
import { apiBase } from "../api/adminClient";
import { readNdjsonLines } from "../api/ndjson";
import type { WorkerEvent } from "../types/domain";

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
