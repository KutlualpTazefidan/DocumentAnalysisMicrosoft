export type BoxKind =
  | "heading"
  | "paragraph"
  | "table"
  | "figure"
  | "caption"
  | "formula"
  | "list_item"
  | "discard";

export type DocStatus = "raw" | "segmenting" | "extracting" | "done" | "needs_ocr";

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
}

export interface DocMeta {
  slug: string;
  filename: string;
  pages: number;
  status: DocStatus;
  last_touched_utc: string;
  box_count: number;
}

export type ExtractLine =
  | { type: "start"; total_boxes: number }
  | { type: "element"; box_id: string; html_snippet: string }
  | { type: "complete"; boxes_extracted: number }
  | { type: "error"; box_id?: string; reason: string };

export type SegmentLine =
  | { type: "start"; total_pages: number }
  | { type: "page"; page: number; boxes_found: number }
  | { type: "complete"; boxes_total: number }
  | { type: "error"; reason: string };

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
