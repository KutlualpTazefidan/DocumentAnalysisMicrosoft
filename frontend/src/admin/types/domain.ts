export type BoxKind =
  | "heading"
  | "paragraph"
  | "table"
  | "figure"
  | "caption"
  | "formula"
  | "list_item"
  | "discard";

export type DocStatus = "raw" | "segmenting" | "extracting" | "extracted" | "synthesising" | "synthesised" | "open-for-curation" | "archived" | "done" | "needs_ocr";

export interface SegmentBox {
  box_id: string;
  page: number;
  bbox: [number, number, number, number];
  kind: BoxKind;
  confidence: number;
  reading_order: number;
}

export interface SegmentsFile {
  slug: string;
  boxes: SegmentBox[];
  /** DPI at which the PDF was rasterized for YOLO inference. bbox coordinates
   * are pixel-space at this DPI. To project onto a PDF.js viewport, multiply
   * bbox by (pdfjsScale * 72 / raster_dpi). Defaults to 144 if absent (legacy
   * pre-2026-05 segment files lacked the field; rasterization was always 144). */
  raster_dpi?: number;
}

export interface DocMeta {
  slug: string;
  filename: string;
  pages: number;
  status: DocStatus;
  last_touched_utc: string;
  box_count: number;
}

export interface SourceElementsPayload {
  doc_slug: string;
  source_pipeline: "local-pdf";
  elements: Array<{
    kind: Exclude<BoxKind, "discard">;
    page: number;
    bbox: [number, number, number, number];
    text: string;
    box_id: string;
    level?: number;
  }>;
}

// ── Curator records ───────────────────────────────────────────────────────

export interface CuratorRecord {
  id: string;
  name: string;
  token_prefix: string;
  created_utc: string;
}

/** Returned only at creation time (C16: full token shown once). */
export interface CuratorCreated extends CuratorRecord {
  token: string;
}

// ── Worker lifecycle events (mirrors local_pdf.workers.base) ──────────────

interface _WorkerEventBase {
  model: string;
  timestamp_ms: number;
}

export interface ModelLoadingEvent extends _WorkerEventBase {
  type: "model-loading";
  source: string;
  vram_estimate_mb: number;
}

export interface ModelLoadedEvent extends _WorkerEventBase {
  type: "model-loaded";
  vram_actual_mb: number;
  load_seconds: number;
}

export interface WorkProgressEvent extends _WorkerEventBase {
  type: "work-progress";
  stage: string;
  current: number;
  total: number;
  eta_seconds: number | null;
  throughput_per_sec: number | null;
  vram_current_mb: number;
}

export interface ModelUnloadingEvent extends _WorkerEventBase {
  type: "model-unloading";
}

export interface ModelUnloadedEvent extends _WorkerEventBase {
  type: "model-unloaded";
  vram_freed_mb: number;
}

export interface WorkCompleteEvent extends _WorkerEventBase {
  type: "work-complete";
  total_seconds: number;
  items_processed: number;
  output_summary: Record<string, unknown>;
}

export interface WorkFailedEvent extends _WorkerEventBase {
  type: "work-failed";
  stage: "load" | "run" | "unload";
  reason: string;
  recoverable: boolean;
  hint: string | null;
}

export type WorkerEvent =
  | ModelLoadingEvent
  | ModelLoadedEvent
  | WorkProgressEvent
  | ModelUnloadingEvent
  | ModelUnloadedEvent
  | WorkCompleteEvent
  | WorkFailedEvent;
