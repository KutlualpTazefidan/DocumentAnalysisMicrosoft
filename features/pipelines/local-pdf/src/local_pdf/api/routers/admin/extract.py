"""Extraction routes: full-doc + region MinerU runs, html GET/PUT, export."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    DocStatus,
    ExtractRegionRequest,
    HtmlPayload,
    WorkFailedEvent,
)
from local_pdf.convert.source_elements import build_source_elements_payload
from local_pdf.storage.sidecar import (
    doc_dir,
    read_html,
    read_meta,
    read_mineru,
    read_segments,
    write_html,
    write_meta,
    write_mineru,
    write_source_elements,
)
from local_pdf.workers.base import now_ms
from local_pdf.workers.mineru import MineruWorker

router = APIRouter()

# Test hook for MinerU.
_MINERU_EXTRACT_FN = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_PDF_STYLE = (
    "<style>"
    "body{font-family:Georgia,'Times New Roman',serif;"
    "max-width:720px;margin:2rem auto;padding:0 2rem;line-height:1.6;color:#1f2937}"
    "h1{font-size:2em;font-weight:bold;text-align:center;margin:1.5em 0 0.5em}"
    "h2{font-size:1.5em;font-weight:bold;margin:1.2em 0 0.4em;"
    "border-bottom:1px solid #d1d5db;padding-bottom:0.2em}"
    "h3{font-size:1.2em;font-weight:bold;margin:1em 0 0.3em}"
    "p{margin:0.6em 0}"
    ".page-header,.page-footer{font-size:0.75em;color:#6b7280;"
    "text-align:center;margin:0.5em 0}"
    ".page-number{display:inline-block;font-size:0.75em;color:#6b7280}"
    ".extracted-table{margin:1em 0;overflow-x:auto}"
    ".extracted-table table{border-collapse:collapse;width:100%}"
    ".extracted-table th,.extracted-table td{"
    "border:1px solid #d1d5db;padding:0.4em 0.6em}"
    # User preference: render <caption> below the table (caption-side:bottom)
    # with a Tab-1-style typography. Click-mapping on the <caption> still
    # routes to the heading user-bbox via _attach_source_box_to_caption.
    ".extracted-table caption{caption-side:bottom;text-align:left;"
    "font-size:0.9em;color:#374151;margin-top:0.4em;font-style:italic}"
    ".toc{margin:1em 0;padding-left:1em}"
    ".md-list{margin:0.6em 0;padding-left:1.5em}"
    "pre{background:#f3f4f6;padding:1em;border-radius:4px;overflow-x:auto}"
    'code{font-family:"SF Mono",Menlo,monospace}'
    "section[data-page]{padding:1em 0}"
    "section[data-page]+section[data-page]{"
    "border-top:2px dashed #d1d5db;margin-top:2em;padding-top:2em}"
    # Caption-rescue marker: a user-bbox sitting adjacent to a table/figure
    # whose caption is already rendered inside that table/figure. Style the
    # reference smaller + italic + muted so it reads as a marker, not a heading.
    ".caption-ref{font-size:0.85em;color:#6b7280;font-style:italic;"
    "margin:0.3em 0;border:none;padding:0}"
    # Visual sub-block captions/footnotes: rendered as <p class="caption">
    # (or "footnote") right next to the table/figure, in their own
    # SegmentBox so they're independently editable.
    "p.caption{font-size:0.9em;color:#374151;font-style:italic;"
    "margin:0.4em 0}"
    "p.footnote{font-size:0.8em;color:#6b7280;margin:0.3em 0}"
    # Body row: vertically-overlapping body items (e.g. two paragraphs at
    # the same y in a 2-column layout) sit side-by-side, sorted by x0.
    ".body-row{display:flex;align-items:flex-start;gap:1rem;margin:0.6em 0}"
    ".body-row > *{flex:1 1 0;min-width:0;margin:0}"
    # Aux stack: page-headers/footers grouped into rows by y-position. Within
    # each row, items land in a 3-column grid (left/center/right) keyed off
    # data-aux-align — so an item left-aligned in the PDF stays left, etc.
    ".aux-stack--top{margin-bottom:1em;padding-bottom:0.4em;"
    "border-bottom:1px solid #e5e7eb}"
    ".aux-stack--bottom{margin-top:1em;padding-top:0.4em;"
    "border-top:1px solid #e5e7eb}"
    ".aux-row{display:grid;grid-template-columns:1fr 1fr 1fr;"
    "align-items:baseline;column-gap:0.5rem}"
    ".aux-row + .aux-row{margin-top:0.2em}"
    ".aux-row > *{margin:0}"
    '.aux-row > [data-aux-align="left"]{grid-column:1;justify-self:start;'
    "text-align:left}"
    '.aux-row > [data-aux-align="center"]{grid-column:2;justify-self:center;'
    "text-align:center}"
    '.aux-row > [data-aux-align="right"]{grid-column:3;justify-self:end;'
    "text-align:right}"
    "</style>"
)


def _page_from_box_id(box_id: str) -> int | None:
    """Return the page number from a box_id like 'p8-b3' → 8."""
    m = re.match(r"p(\d+)-", box_id or "")
    return int(m.group(1)) if m else None


_AUX_ZONE_RE = re.compile(r'data-aux-zone="(header|footer)"')
_X_RE = re.compile(r'data-x="(\d+)"')
_Y_RE = re.compile(r'data-y="(\d+)"')
_Y1_RE = re.compile(r'data-y1="(\d+)"')


def _group_aux_into_rows(
    items: list[tuple[int, int, int, str]],
) -> list[list[str]]:
    """Group items into rows by visual-line proximity (y0 distance).

    "Same row" really means "items on the same visual line." MinerU's bbox
    y-ranges sometimes touch or overlap by 1-2pt between adjacent lines
    (because letter ascenders/descenders straddle line boundaries). Pure
    bbox-overlap then chains the touching lines into one row.

    Instead, anchor each row on its FIRST item's ``y0`` and admit a new
    candidate iff its ``y0`` differs from that anchor by no more than half
    the smaller item's height (with a 2pt floor for OCR jitter). Items
    starting at clearly different y0 land on separate visual lines even
    if their bboxes overlap by a sliver.

    Items: ``(y0, y1, x0, snippet)``. Within each row, sort by x0 so DOM
    order matches PDF column order.
    """
    if not items:
        return []
    sorted_items = sorted(items, key=lambda t: (t[0], t[2]))
    rows: list[list[tuple[int, int, int, str]]] = [[sorted_items[0]]]
    for entry in sorted_items[1:]:
        y0, y1, _x, _snippet = entry
        anchor_y0, anchor_y1, _, _ = rows[-1][0]
        h_min = min(y1 - y0, anchor_y1 - anchor_y0)
        tol = max(2, h_min // 2)
        if abs(y0 - anchor_y0) <= tol:
            rows[-1].append(entry)
        else:
            rows.append([entry])
    return [[s for _, _, _, s in sorted(row, key=lambda t: t[2])] for row in rows]


def _partition_aux(
    snippets: list[str],
) -> tuple[list[list[str]], list[str], list[list[str]]]:
    """Split per-page snippets into (header_rows, content, footer_rows).

    Aux snippets carry ``data-aux-zone`` plus the universal positional
    attrs ``data-x`` / ``data-y`` / ``data-y1``. Items whose vertical
    ranges overlap share a row; non-overlapping items stack.
    """
    header_aux: list[tuple[int, int, int, str]] = []
    footer_aux: list[tuple[int, int, int, str]] = []
    content: list[str] = []
    for s in snippets:
        zm = _AUX_ZONE_RE.search(s)
        if not zm:
            content.append(s)
            continue
        xm = _X_RE.search(s)
        ym0 = _Y_RE.search(s)
        ym1 = _Y1_RE.search(s)
        x = int(xm.group(1)) if xm else 0
        y0 = int(ym0.group(1)) if ym0 else 0
        y1 = int(ym1.group(1)) if ym1 else y0
        target = header_aux if zm.group(1) == "header" else footer_aux
        target.append((y0, y1, x, s))
    return _group_aux_into_rows(header_aux), content, _group_aux_into_rows(footer_aux)


def _group_body_into_rows(snippets: list[str]) -> list[list[str]]:
    """Group body snippets by vertical-bbox overlap, sort each row by x0.

    Reuses ``_group_aux_into_rows`` after extracting positional attrs.
    Snippets without ``data-y``/``data-y1`` (e.g. legacy elements) get a
    single-item row preserving their original order.
    """
    items: list[tuple[int, int, int, str]] = []
    fallback_idx = 0
    for s in snippets:
        ym0 = _Y_RE.search(s)
        ym1 = _Y1_RE.search(s)
        xm = _X_RE.search(s)
        if ym0 is None:
            # No positional metadata — keep in original order, treat as
            # standalone row by giving it a unique ascending y key.
            fallback_idx += 1
            items.append((10_000_000 + fallback_idx, 10_000_000 + fallback_idx, 0, s))
            continue
        y0 = int(ym0.group(1))
        y1 = int(ym1.group(1)) if ym1 else y0
        x = int(xm.group(1)) if xm else 0
        items.append((y0, y1, x, s))
    return _group_aux_into_rows(items)


def _wrap_body_rows(rows: list[list[str]]) -> str:
    """Render body rows: single-item rows emit their snippet raw, multi-item
    rows wrap in a flex ``<div class="body-row">`` so vertically-overlapping
    items lay out left-to-right by x0."""
    parts: list[str] = []
    for row in rows:
        if len(row) == 1:
            parts.append(row[0])
        else:
            parts.append(f'<div class="body-row">{"".join(row)}</div>')
    return "".join(parts)


def _wrap_aux_stack(rows: list[list[str]], position: str) -> str:
    """Wrap aux rows in a stack container; each row is its own grid container."""
    if not rows:
        return ""
    inner = "".join(f'<div class="aux-row">{"".join(row)}</div>' for row in rows)
    return f'<div class="aux-stack aux-stack--{position}">{inner}</div>'


def _group_list_items(section_inner: str) -> str:
    """Wrap consecutive <li ...>...</li> blocks in a single <ul>...</ul>.

    Adjacent list items emitted by the worker (one ``<li>`` per user box) are
    grouped so the rendered HTML has proper ``<ul>`` structure.  Non-adjacent
    list items each get their own ``<ul>``.

    The input is controlled (worker output only), so a regex over the fragment
    is sufficient — no full HTML parser needed.
    """
    return re.sub(
        r"(<li\b[^>]*>.*?</li>(?:\s*<li\b[^>]*>.*?</li>)*)",
        r"<ul>\1</ul>",
        section_inner,
        flags=re.DOTALL,
    )


def _wrap_html(elements: list[dict]) -> str:
    """Wrap extracted HTML snippets with PDF-like typography and page sections.

    Groups elements by page number (derived from box_id prefix ``pN-bM``) and
    wraps each group in ``<section data-page="{N}">`` so the frontend can slice
    by page number instead of relying on brittle hr-count indexing.

    Adjacent ``<li>`` elements within a section are wrapped in a single
    ``<ul>`` via ``_group_list_items``.
    """
    by_page: dict[int, list[str]] = {}
    page_order: list[int] = []
    for e in elements:
        page = _page_from_box_id(e.get("box_id", ""))
        if page is None:
            continue
        if page not in by_page:
            by_page[page] = []
            page_order.append(page)
        by_page[page].append(e["html_snippet"])

    sections = []
    for p in page_order:
        header_aux, content, footer_aux = _partition_aux(by_page[p])
        # Group body content by vertical bbox overlap so multi-column layouts
        # (or any same-y items) lay out side-by-side. _group_list_items must
        # run on the full body string AFTER row wrapping so consecutive <li>
        # are still wrapped in <ul> when they fall in the same row.
        body_rows = _group_body_into_rows(content)
        body_html = _group_list_items(_wrap_body_rows(body_rows))
        inner = (
            _wrap_aux_stack(header_aux, "top") + body_html + _wrap_aux_stack(footer_aux, "bottom")
        )
        sections.append(f'<section data-page="{p}">\n{inner}\n</section>')
    body = "\n".join(sections)
    return f"<!DOCTYPE html>\n<html><head>{_PDF_STYLE}</head><body>\n{body}\n</body></html>\n"


def _merge_elements(existing: list[dict], new_elements: list[dict]) -> list[dict]:
    """Merge *new_elements* into *existing*, replacing any with matching box_id.

    Preserves the order of existing elements; appends genuinely new box_ids at
    the end in the order they appear in *new_elements*.
    """
    by_id = {e["box_id"]: e for e in existing}
    for e in new_elements:
        by_id[e["box_id"]] = e
    # Rebuild: existing order first, then any new box_ids not previously present.
    seen: set[str] = set()
    result: list[dict] = []
    for e in existing:
        bid = e["box_id"]
        result.append(by_id[bid])
        seen.add(bid)
    for e in new_elements:
        bid = e["box_id"]
        if bid not in seen:
            result.append(by_id[bid])
            seen.add(bid)
    return result


@router.post("/api/admin/docs/{slug}/extract")
async def run_extract(slug: str, request: Request, page: int | None = None) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(
                update={"status": DocStatus.extracting, "last_touched_utc": _now_iso()}
            ),
        )

    targets = [b for b in seg.boxes if b.kind != BoxKind.discard]
    if page is not None:
        targets = [b for b in targets if b.page == page]

    def stream():
        try:
            with MineruWorker(
                extract_fn=_MINERU_EXTRACT_FN,
                raster_dpi=seg.raster_dpi,
                image_writer_dir=doc_dir(cfg.data_root, slug) / "mineru-images",
            ) as worker:
                for ev in worker.run(pdf, targets):
                    # Persist after each yielded WorkProgressEvent's box result.
                    yield ev.model_dump_json() + "\n"
                # Build elements list from worker.results.
                new_elements = [
                    {"box_id": r.box_id, "html_snippet": r.html} for r in worker.results
                ]
                # Per-run diagnostics from the assignment helper (split / no-decomposition events).
                new_diagnostics = list(worker.diagnostics or [])
                if page is not None:
                    # Partial extraction: WIPE this page's existing elements
                    # before applying the new ones. Otherwise boxes that used
                    # to be active but were since deactivated (kind=discard)
                    # would keep their stale html_snippet on disk because
                    # `targets` excludes discards and the new run doesn't
                    # produce a replacement. Per-page replace = the user's
                    # current activate/deactivate state always wins.
                    existing_data = read_mineru(cfg.data_root, slug)
                    existing_elements = existing_data["elements"] if existing_data else []
                    other_pages = [
                        e
                        for e in existing_elements
                        if _page_from_box_id(e.get("box_id", "")) != page
                    ]
                    merged = other_pages + new_elements
                    existing_diags = existing_data.get("diagnostics", []) if existing_data else []
                    kept_diags = [d for d in existing_diags if d.get("page") != page]
                    merged_diagnostics = kept_diags + new_diagnostics
                else:
                    merged = new_elements
                    merged_diagnostics = new_diagnostics
                write_mineru(
                    cfg.data_root,
                    slug,
                    {"elements": merged, "diagnostics": merged_diagnostics},
                )
                write_html(cfg.data_root, slug, _wrap_html(merged))
                for ev in worker.unload():
                    yield ev.model_dump_json() + "\n"
        except Exception as exc:
            failure = WorkFailedEvent(
                model=MineruWorker.name,
                timestamp_ms=now_ms(),
                stage="run",
                reason=str(exc),
                recoverable=False,
                hint=None,
            )
            yield failure.model_dump_json() + "\n"
            raise

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/admin/docs/{slug}/extract/region")
async def run_extract_region(slug: str, body: ExtractRegionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    target = next((b for b in seg.boxes if b.box_id == body.box_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")
    with MineruWorker(
        extract_fn=_MINERU_EXTRACT_FN,
        raster_dpi=seg.raster_dpi,
        image_writer_dir=doc_dir(cfg.data_root, slug) / "mineru-images",
    ) as worker:
        result = worker.extract_region(pdf, target)
    return {"box_id": result.box_id, "html": result.html}


@router.get("/api/admin/docs/{slug}/mineru")
async def get_mineru(slug: str, request: Request) -> dict:
    """Return the stored MinerU extraction output (mineru-out.json).

    Used by the frontend to compute per-page extraction state for the
    colored page-button grid.  Returns 404 when no extraction has been
    run yet.
    """
    cfg = request.app.state.config
    data = read_mineru(cfg.data_root, slug)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no mineru data for {slug}")
    return data


@router.get("/api/admin/docs/{slug}/html")
async def get_html(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=404, detail=f"no html for {slug}")
    return {"html": html}


@router.put("/api/admin/docs/{slug}/html")
async def put_html(slug: str, body: HtmlPayload, request: Request) -> dict:
    cfg = request.app.state.config
    if not (doc_dir(cfg.data_root, slug)).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    write_html(cfg.data_root, slug, body.html)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))
    return {"ok": True}


@router.get("/api/admin/docs/{slug}/extract/diagnose")
async def diagnose_extract(slug: str, request: Request, page: int = 1) -> dict:
    """Diagnostic: parse one page via MinerU and return raw bbox + text data.

    Returns the MinerU para_block bboxes alongside their IoU against each
    segment box on that page, so the caller can verify coordinate alignment
    without running a full extraction.

    Response shape::

        {
          "page": 1,
          "raster_dpi": 144,
          "page_size_pts": [728, 927],
          "mineru_blocks": [
            {"type": "title", "bbox": [198, 145, 527, 178],
             "text_preview": "A Study of...",
             "iou_to_user_boxes": [{"box_id": "p1-b0", "iou": 0.87}]}
          ]
        }
    """
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    raster_dpi = seg.raster_dpi if seg is not None else 288

    try:
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze_streaming
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
            merge_para_with_text,
            merge_visual_blocks_to_markdown,
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"MinerU not available: {exc}") from exc

    pdf_bytes = pdf.read_bytes()
    all_page_infos: list[dict] = []

    class _NullWriter:
        def write(self, *_a: object, **_kw: object) -> None:
            pass

    def _on_ready(
        doc_index: int,
        model_list: list,
        middle_json: dict,
        ocr_enable: bool,
    ) -> None:
        pdf_info = middle_json.get("pdf_info", [])
        all_page_infos.extend(pdf_info)

    doc_analyze_streaming(
        pdf_bytes_list=[pdf_bytes],
        image_writer_list=[_NullWriter()],
        lang_list=[None],
        on_doc_ready=_on_ready,
        parse_method="auto",
    )

    if page < 1 or page > len(all_page_infos):
        raise HTTPException(
            status_code=404,
            detail=f"page {page} out of range (1-{len(all_page_infos)})",
        )

    page_info = all_page_infos[page - 1]
    page_size = page_info.get("page_size") or [0, 0]

    # Build user-bbox-to-pts lookup for IoU comparison.
    from local_pdf.workers.mineru import _iou, _user_bbox_to_pts

    user_boxes_pts: list[tuple[str, tuple[float, float, float, float]]] = []
    if seg is not None:
        for b in seg.boxes:
            if b.page == page:
                user_boxes_pts.append((b.box_id, _user_bbox_to_pts(b.bbox, raster_dpi)))

    visual_block_types = {"image", "table", "chart", "code"}
    blocks_out = []
    for blk in page_info.get("para_blocks", []) or []:
        raw_bbox = blk.get("bbox")
        if raw_bbox is None:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in raw_bbox[:4])
        except (TypeError, ValueError):
            continue
        blk_type = blk.get("type", "unknown")
        try:
            if blk_type in visual_block_types:
                text = merge_visual_blocks_to_markdown(blk) or ""
            else:
                text = merge_para_with_text(blk) or ""
        except Exception:
            text = ""
        iou_scores: list[tuple[float, str]] = [
            (_iou((x0, y0, x1, y1), bpts), bid) for bid, bpts in user_boxes_pts
        ]
        iou_scores.sort(key=lambda t: -t[0])
        iou_list = [{"box_id": bid, "iou": round(score, 4)} for score, bid in iou_scores[:5]]
        blocks_out.append(
            {
                "type": blk_type,
                "bbox": [x0, y0, x1, y1],
                "text_preview": text[:120],
                "iou_to_user_boxes": iou_list,
            }
        )

    return {
        "page": page,
        "raster_dpi": raster_dpi,
        "page_size_pts": page_size,
        "mineru_blocks": blocks_out,
    }


@router.post("/api/admin/docs/{slug}/export")
async def run_export(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=400, detail="run /extract first")
    payload = build_source_elements_payload(slug=slug, segments=seg, html=html)
    write_source_elements(cfg.data_root, slug, payload)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(update={"status": DocStatus.done, "last_touched_utc": _now_iso()}),
        )
    return payload


@router.get("/api/admin/docs/{slug}/page-image")
async def get_page_image(
    slug: str,
    request: Request,
    page: int = 1,
    dpi: int | None = None,
) -> Response:
    """Render a single PDF page as PNG at the given DPI (default = seg.raster_dpi).

    Useful for inspecting what YOLO / MinerU see as input. Mirrors the
    rasterization YOLO uses (pdfplumber `to_image(resolution=dpi)`).
    """
    import io

    import pdfplumber

    cfg = request.app.state.config
    pdf_path = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")

    if dpi is None:
        seg = read_segments(cfg.data_root, slug)
        dpi = seg.raster_dpi if seg is not None else 288

    with pdfplumber.open(str(pdf_path)) as pdf:
        if page < 1 or page > len(pdf.pages):
            raise HTTPException(status_code=404, detail=f"page out of range: {page}")
        im = pdf.pages[page - 1].to_image(resolution=dpi).original
        buf = io.BytesIO()
        im.save(buf, format="PNG")

    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/api/admin/docs/{slug}/mineru-images/{filename}")
async def get_mineru_image(slug: str, filename: str, request: Request) -> FileResponse:
    """Serve a single image cropout MinerU saved during extraction.

    Files live under ``outputs/{slug}/mineru-images/`` (figures, tables,
    formulas etc.). Filename traversal is rejected.
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    cfg = request.app.state.config
    path = doc_dir(cfg.data_root, slug) / "mineru-images" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"image not found: {filename}")
    return FileResponse(path)


@router.get("/api/admin/docs/{slug}/mineru-images")
async def list_mineru_images(slug: str, request: Request) -> dict:
    """List image cropouts MinerU saved during extraction for this doc."""
    cfg = request.app.state.config
    img_dir = doc_dir(cfg.data_root, slug) / "mineru-images"
    if not img_dir.exists():
        return {"images": []}
    files = sorted(p.name for p in img_dir.iterdir() if p.is_file())
    return {"images": files}
