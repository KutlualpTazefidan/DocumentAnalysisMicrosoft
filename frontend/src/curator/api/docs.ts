import { apiFetch, rawFetch } from "./curatorClient";
import type {
  DocSummary,
  ElementWithCounts,
  DocumentElement,
  RetrievalEntry,
  SynthesiseRequest,
  SynthLine,
} from "../../shared/types/domain";
import { streamNdjson } from "./ndjson";

export async function listDocs(): Promise<DocSummary[]> {
  return apiFetch<DocSummary[]>("/api/docs");
}

export async function listElements(slug: string): Promise<ElementWithCounts[]> {
  return apiFetch<ElementWithCounts[]>(
    `/api/docs/${encodeURIComponent(slug)}/elements`,
  );
}

export interface ElementDetailResponse {
  element: DocumentElement;
  entries: RetrievalEntry[];
}

export async function getElement(
  slug: string,
  elementId: string,
): Promise<ElementDetailResponse> {
  return apiFetch<ElementDetailResponse>(
    `/api/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elementId)}`,
  );
}

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
