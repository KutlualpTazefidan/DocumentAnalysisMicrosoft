import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exportSourceElements, extractRegion, getHtml, putHtml } from "../api/docs";
import { apiBase } from "../api/client";
import { readNdjsonLines } from "../api/ndjson";
import type { ExtractLine, SegmentLine } from "../types/domain";

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

export async function* streamSegment(slug: string, token: string): AsyncGenerator<SegmentLine> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/segment`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<SegmentLine>(r.body);
}

export async function* streamExtract(slug: string, token: string): AsyncGenerator<ExtractLine> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/extract`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<ExtractLine>(r.body);
}
