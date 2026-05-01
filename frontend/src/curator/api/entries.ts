import { apiFetch } from "./curatorClient";
import type {
  CreateEntryRequest,
  CreateEntryResponse,
  DeprecateRequest,
  DeprecateResponse,
  RefineRequest,
  RefineResponse,
  RetrievalEntry,
} from "../../shared/types/domain";

export interface ListEntriesParams {
  slug?: string;
  source_element?: string;
  include_deprecated?: boolean;
}

export async function listEntries(
  params: ListEntriesParams = {},
): Promise<RetrievalEntry[]> {
  const qs = new URLSearchParams();
  if (params.slug) qs.set("slug", params.slug);
  if (params.source_element) qs.set("source_element", params.source_element);
  if (params.include_deprecated)
    qs.set("include_deprecated", String(params.include_deprecated));
  const query = qs.toString();
  return apiFetch<RetrievalEntry[]>(
    `/api/entries${query ? `?${query}` : ""}`,
  );
}

export async function getEntry(entryId: string): Promise<RetrievalEntry> {
  return apiFetch<RetrievalEntry>(
    `/api/entries/${encodeURIComponent(entryId)}`,
  );
}

export async function createEntry(
  slug: string,
  elementId: string,
  body: CreateEntryRequest,
): Promise<CreateEntryResponse> {
  return apiFetch<CreateEntryResponse>(
    `/api/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elementId)}/entries`,
    { method: "POST", body },
  );
}

export async function refineEntry(
  entryId: string,
  body: RefineRequest,
): Promise<RefineResponse> {
  return apiFetch<RefineResponse>(
    `/api/entries/${encodeURIComponent(entryId)}/refine`,
    { method: "POST", body },
  );
}

export async function deprecateEntry(
  entryId: string,
  body: DeprecateRequest,
): Promise<DeprecateResponse> {
  return apiFetch<DeprecateResponse>(
    `/api/entries/${encodeURIComponent(entryId)}/deprecate`,
    { method: "POST", body },
  );
}
