import { apiFetch } from "./adminClient";
import type { CuratorCreated, CuratorRecord, DocMeta, SegmentBox, SegmentsFile, SourceElementsPayload, BoxKind } from "../types/domain";

export async function listDocs(token: string): Promise<DocMeta[]> {
  const r = await apiFetch("/api/admin/docs", token);
  return r.json();
}

export async function uploadDoc(file: File, token: string): Promise<DocMeta> {
  const fd = new FormData();
  fd.set("file", file);
  const r = await apiFetch("/api/admin/docs", token, { method: "POST", body: fd });
  return r.json();
}

export async function getDoc(slug: string, token: string): Promise<DocMeta> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}`, token);
  return r.json();
}

export async function getSegments(slug: string, token: string): Promise<SegmentsFile> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/segments`, token);
  return r.json();
}

export async function updateBox(
  slug: string,
  boxId: string,
  patch: { kind?: BoxKind; bbox?: [number, number, number, number]; reading_order?: number },
  token: string,
): Promise<SegmentBox> {
  const r = await apiFetch(
    `/api/admin/docs/${encodeURIComponent(slug)}/segments/${encodeURIComponent(boxId)}`,
    token,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) },
  );
  return r.json();
}

export async function deleteBox(slug: string, boxId: string, token: string): Promise<SegmentBox> {
  const r = await apiFetch(
    `/api/admin/docs/${encodeURIComponent(slug)}/segments/${encodeURIComponent(boxId)}`,
    token,
    { method: "DELETE" },
  );
  return r.json();
}

export async function mergeBoxes(slug: string, boxIds: string[], token: string): Promise<SegmentBox> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/segments/merge`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_ids: boxIds }),
  });
  return r.json();
}

export async function splitBox(slug: string, boxId: string, splitY: number, token: string): Promise<{ top: SegmentBox; bottom: SegmentBox }> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/segments/split`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_id: boxId, split_y: splitY }),
  });
  return r.json();
}

export async function createBox(slug: string, page: number, bbox: [number, number, number, number], kind: BoxKind, token: string): Promise<SegmentBox> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/segments`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page, bbox, kind }),
  });
  return r.json();
}

export async function getHtml(slug: string, token: string): Promise<string> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/html`, token);
  const j = (await r.json()) as { html: string };
  return j.html;
}

export async function putHtml(slug: string, html: string, token: string): Promise<void> {
  await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/html`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
}

export async function exportSourceElements(slug: string, token: string): Promise<SourceElementsPayload> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/export`, token, { method: "POST" });
  return r.json();
}

export async function extractRegion(slug: string, boxId: string, token: string): Promise<{ box_id: string; html: string }> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/extract/region`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_id: boxId }),
  });
  return r.json();
}

export async function publishDoc(slug: string, token: string): Promise<DocMeta> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/publish`, token, { method: "POST" });
  return r.json();
}

export async function archiveDoc(slug: string, token: string): Promise<DocMeta> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/archive`, token, { method: "POST" });
  return r.json();
}

// ── Curator API ───────────────────────────────────────────────────────────

export async function listCurators(token: string): Promise<CuratorRecord[]> {
  const r = await apiFetch("/api/admin/curators", token);
  return r.json();
}

export async function createCurator(name: string, token: string): Promise<CuratorCreated> {
  const r = await apiFetch("/api/admin/curators", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return r.json();
}

export async function revokeCurator(id: string, token: string): Promise<void> {
  await apiFetch(`/api/admin/curators/${encodeURIComponent(id)}`, token, { method: "DELETE" });
}

export async function listDocCurators(slug: string, token: string): Promise<CuratorRecord[]> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/curators`, token);
  return r.json();
}

export async function assignCurator(slug: string, curatorId: string, token: string): Promise<CuratorRecord> {
  const r = await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/curators`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ curator_id: curatorId }),
  });
  return r.json();
}

export async function unassignCurator(slug: string, curatorId: string, token: string): Promise<void> {
  await apiFetch(`/api/admin/docs/${encodeURIComponent(slug)}/curators/${encodeURIComponent(curatorId)}`, token, {
    method: "DELETE",
  });
}
