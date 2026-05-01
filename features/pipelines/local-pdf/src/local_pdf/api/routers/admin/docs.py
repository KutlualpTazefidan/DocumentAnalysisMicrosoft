"""Admin doc routes: inbox listing, upload, metadata, source PDF serving."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from local_pdf.api.schemas import DocMeta, DocStatus
from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta
from local_pdf.storage.slug import unique_slug

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_pages(pdf_path) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as p:
            return len(p.pages)
    except Exception:
        return 1


@router.get("/api/admin/docs")
async def list_docs(request: Request) -> list[dict]:
    cfg = request.app.state.config
    out: list[dict] = []
    if not cfg.data_root.exists():
        return out
    for entry in sorted(cfg.data_root.iterdir()):
        if not entry.is_dir():
            continue
        meta = read_meta(cfg.data_root, entry.name)
        if meta is not None:
            out.append(meta.model_dump(mode="json"))
    return out


@router.post("/api/admin/docs", status_code=201)
async def upload_doc(request: Request, file: UploadFile) -> JSONResponse:
    cfg = request.app.state.config
    filename = file.filename or "untitled.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF uploads accepted")
    blob = await file.read()
    if not blob.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="not a PDF (missing %PDF magic)")

    slug = unique_slug(cfg.data_root, filename)
    target = doc_dir(cfg.data_root, slug)
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
    write_meta(cfg.data_root, slug, meta)
    return JSONResponse(status_code=201, content=meta.model_dump(mode="json"))


@router.get("/api/admin/docs/{slug}")
async def get_doc(slug: str, request: Request) -> dict[str, object]:
    cfg = request.app.state.config
    meta = read_meta(cfg.data_root, slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    return meta.model_dump(mode="json")  # type: ignore[no-any-return]


@router.get("/api/admin/docs/{slug}/source.pdf")
async def get_source_pdf(slug: str, request: Request) -> FileResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    return FileResponse(str(pdf), media_type="application/pdf")
