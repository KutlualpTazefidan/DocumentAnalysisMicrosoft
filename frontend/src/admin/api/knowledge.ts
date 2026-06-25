import { apiBase, apiFetch } from "./adminClient";

export interface BaseSummary { name: string; title: string; concept_count: number }
export interface ConceptSummary { path: string; type: string; title: string; tags: string[] }
export interface ConceptLink { text: string; path: string; resolved: boolean }
export interface Concept {
  path: string; type: string; title: string; description: string;
  timestamp: string; tags: string[]; body: string;
  links: ConceptLink[]; malformed: boolean;
}

export async function listBases(token: string): Promise<BaseSummary[]> {
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases`, token)).json();
}

export async function listConcepts(base: string, token: string): Promise<ConceptSummary[]> {
  const b = encodeURIComponent(base);
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases/${b}/concepts`, token)).json();
}

export async function getConcept(base: string, path: string, token: string): Promise<Concept> {
  const b = encodeURIComponent(base);
  const p = encodeURIComponent(path);
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases/${b}/concept?path=${p}`, token)).json();
}
