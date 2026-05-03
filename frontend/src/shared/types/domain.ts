export type ElementType = "paragraph" | "heading" | "table" | "figure" | "list_item";

export type Level = "expert" | "phd" | "masters" | "bachelors" | "other";
export type ComputedLevel = Level | "synthetic";

export type CreateAction = "created_from_scratch" | "synthesised" | "imported_from_faq";

export interface SourceElement {
  document_id: string;
  page_number: number;
  element_id: string;          // bare hash (sans p{page}- prefix)
  element_type: ElementType;
}

export interface DocumentElement {
  element_id: string;          // p{page}-<hash>
  page_number: number;
  element_type: ElementType;
  content: string;
  table_dims?: [number, number];
  table_full_content?: string | null;
  caption?: string | null;
}

export interface HumanActor {
  kind: "human";
  pseudonym: string;
  level: Level;
}

export interface LLMActor {
  kind: "llm";
  model: string;
  model_version: string;
  prompt_template_version: string;
  temperature: number;
}

export type Actor = HumanActor | LLMActor;

export interface Review {
  timestamp_utc: string;
  action: string;
  actor: Actor;
  notes: string | null;
}

export interface RetrievalEntry {
  entry_id: string;
  query: string;
  expected_chunk_ids: string[];
  chunk_hashes: Record<string, string>;
  review_chain: Review[];
  deprecated: boolean;
  refines: string | null;
  task_type: "retrieval";
  source_element: SourceElement | null;
}

export interface ElementWithCounts {
  element: DocumentElement;
  count_active_entries: number;
}

export interface DocSummary {
  slug: string;
  element_count: number;
}

export interface DocMeta {
  slug: string;
  filename: string;
  pages: number;
  status: string;
  last_touched_utc: string;
  box_count: number;
}

// Synthesise streaming line types
export interface SynthStartLine {
  type: "start";
  total_elements: number;
}

export interface SynthElementLine {
  type: "element";
  element_id: string;
  kept: number;
  skipped_reason: string | null;
  tokens_estimated: number;
}

export interface SynthCompleteLine {
  type: "complete";
  events_written: number;
  prompt_tokens_estimated: number;
}

export interface SynthErrorLine {
  type: "error";
  element_id: string | null;
  reason: string;
}

export type SynthLine =
  | SynthStartLine
  | SynthElementLine
  | SynthCompleteLine
  | SynthErrorLine;

// Request bodies
export interface CreateEntryRequest {
  query: string;
}

export interface RefineRequest {
  query: string;
  expected_chunk_ids?: string[];
  chunk_hashes?: Record<string, string>;
  notes?: string | null;
  deprecate_reason?: string | null;
}

export interface DeprecateRequest {
  reason?: string | null;
}

export interface SynthesiseRequest {
  llm_model: string;
  llm_base_url?: string | null;
  dry_run?: boolean;
  max_questions_per_element?: number;
  max_prompt_tokens?: number;
  prompt_template_version?: string;
  temperature?: number;
  start_from?: string | null;
  limit?: number | null;
  embedding_model?: string | null;
  resume?: boolean;
}

// Response wrappers
export interface CreateEntryResponse {
  entry_id: string;
  event_id: string;
}

export interface RefineResponse {
  new_entry_id: string;
}

export interface DeprecateResponse {
  event_id: string;
}

export interface HealthResponse {
  status: "ok";
  goldens_root: string;
}
