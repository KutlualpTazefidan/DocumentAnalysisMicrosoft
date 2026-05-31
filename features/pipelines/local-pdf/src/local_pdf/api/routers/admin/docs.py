"""Admin doc routes: inbox listing, upload, metadata, source PDF serving."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from local_pdf.api.schemas import (
    DocMeta,
    DocStatus,
    PageStatus,
    PageStatusFile,
    SetPageStatusRequest,
)
from local_pdf.auth.tenant_root import tenant_data_root, tenant_slug_from_request
from local_pdf.storage.sidecar import (
    doc_dir,
    read_meta,
    read_page_status,
    update_page_status,
    write_meta,
)
from local_pdf.storage.slug import unique_slug

router = APIRouter()


def _tr(request: Request):
    """Tenant-aware data_root for the active request. Cookie-mode
    users in tenant != default get data_root/tenants/{slug}/; legacy
    callers see the bare data_root."""
    raw = request.app.state.config.data_root
    return tenant_data_root(raw, tenant_slug_from_request(request))


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _touch_meta(data_root, slug: str) -> None:
    """Bump ONLY ``last_touched_utc`` on a doc's meta (no-op if meta missing).

    Mirrors the put_html pattern in extract.py — deliberately does NOT touch
    DocStatus. Per-page status is orthogonal to DocStatus, so toggling a page's
    done-bit must never advance/regress the document lifecycle.
    """
    meta = read_meta(data_root, slug)
    if meta is not None:
        write_meta(data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))


def _count_pages(pdf_path) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as p:
            return len(p.pages)
    except Exception:
        return 1


@router.get("/api/admin/docs")
async def list_docs(request: Request) -> list[dict]:
    out: list[dict] = []
    if not _tr(request).exists():
        return out
    for entry in sorted(_tr(request).iterdir()):
        if not entry.is_dir():
            continue
        meta = read_meta(_tr(request), entry.name)
        if meta is not None:
            out.append(meta.model_dump(mode="json"))
    return out


@router.post("/api/admin/docs", status_code=201)
async def upload_doc(request: Request, file: UploadFile) -> JSONResponse:
    filename = file.filename or "untitled.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF uploads accepted")
    blob = await file.read()
    if not blob.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="not a PDF (missing %PDF magic)")

    slug = unique_slug(_tr(request), filename)
    target = doc_dir(_tr(request), slug)
    target.mkdir(parents=True, exist_ok=True)
    pdf_path = target / "source.pdf"
    pdf_path.write_bytes(blob)
    pages = _count_pages(pdf_path)
    meta = DocMeta(
        slug=slug,
        filename=filename,
        pages=max(pages, 1),
        status=DocStatus.raw,
        last_touched_utc=_now_iso(),
    )
    write_meta(_tr(request), slug, meta)
    return JSONResponse(status_code=201, content=meta.model_dump(mode="json"))


@router.get("/api/admin/docs/{slug}")
async def get_doc(slug: str, request: Request) -> dict[str, object]:
    meta = read_meta(_tr(request), slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    return meta.model_dump(mode="json")  # type: ignore[no-any-return]


@router.get("/api/admin/docs/{slug}/source.pdf")
async def get_source_pdf(slug: str, request: Request) -> FileResponse:
    pdf = doc_dir(_tr(request), slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    return FileResponse(str(pdf), media_type="application/pdf")


@router.post("/api/admin/docs/{slug}/publish")
async def publish_doc(slug: str, request: Request) -> dict[str, object]:
    meta = read_meta(_tr(request), slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    new = meta.model_copy(
        update={
            "status": DocStatus.open_for_curation,
            "last_touched_utc": _now_iso(),
        }
    )
    write_meta(_tr(request), slug, new)
    return new.model_dump(mode="json")  # type: ignore[no-any-return]


@router.post("/api/admin/docs/{slug}/archive")
async def archive_doc(slug: str, request: Request) -> dict[str, object]:
    meta = read_meta(_tr(request), slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    new = meta.model_copy(
        update={
            "status": DocStatus.archived,
            "last_touched_utc": _now_iso(),
        }
    )
    write_meta(_tr(request), slug, new)
    return new.model_dump(mode="json")  # type: ignore[no-any-return]


@router.get("/api/admin/docs/{slug}/pages/status")
async def get_page_status(slug: str, request: Request) -> dict[str, object]:
    """Return the per-doc page-status sidecar (the set of done pages).

    404 when the doc is unknown. When no sidecar exists yet, returns an empty
    ``done_pages`` list. Per-page status is orthogonal to DocStatus.
    """
    meta = read_meta(_tr(request), slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    payload = read_page_status(_tr(request), slug) or PageStatusFile(slug=slug, done_pages=[])
    return payload.model_dump(mode="json")  # type: ignore[no-any-return]


@router.patch("/api/admin/docs/{slug}/pages/{page}/status")
async def set_page_status(
    slug: str, page: int, body: SetPageStatusRequest, request: Request
) -> dict[str, object]:
    """Toggle a single page's done-bit.

    ``status == done`` persists the page in the sidecar; any other status
    removes it (in_progress/not_started are derived client-side, never stored).
    Bumps ``last_touched_utc`` but never changes DocStatus. 404 unknown doc;
    400 when *page* is out of range.
    """
    meta = read_meta(_tr(request), slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    if page < 1 or page > meta.pages:
        raise HTTPException(status_code=400, detail=f"page {page} out of range (1-{meta.pages})")
    update_page_status(_tr(request), slug, page, body.status == PageStatus.done)
    _touch_meta(_tr(request), slug)
    return {"page": page, "status": body.status.value}


@router.delete("/api/admin/docs/{slug}", status_code=204)
async def delete_doc(slug: str, request: Request) -> JSONResponse:
    """Delete a document and ALL of its sidecar artefacts.

    Wipes ``outputs/{slug}/`` (or whatever ``data_root/{slug}`` resolves to):
    source.pdf, meta.json, segments.json, mineru.json, html.html,
    sourceelements.json, mineru-images/, etc.

    Returns 204 on success, 404 if the slug doesn't exist.
    """
    import shutil

    target = doc_dir(_tr(request), slug)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    # Refuse to nuke anything outside data_root via path traversal in slug.
    try:
        target.resolve().relative_to(_tr(request).resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid slug path") from exc
    shutil.rmtree(target)
    return JSONResponse(status_code=204, content=None)
