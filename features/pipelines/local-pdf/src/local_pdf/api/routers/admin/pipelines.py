"""External-pipeline runner — the "right pane" of the Vergleich tab.

Two pipelines:

  microsoft → Document Intelligence + Azure AI Search ingestion
              + hybrid retrieval + Azure OpenAI completion. The
              ingestion side is "knowledge sources": you upload a PDF
              once, run analyze → chunk → embed → upload, then later
              ask questions scoped to that source.

  bam       → Stub. 501 until wired.

The route layer here is a thin adapter: it calls into the Microsoft
package and shapes the response. No local_pdf state is mutated by
ask, and no goldens events are written — comparison is read-only
against external pipelines. Knowledge-source artifacts live under
``{LOCAL_PDF_DATA_ROOT}/microsoft-sources/{slug}/`` so a slug's
ingestion data can be wiped with a single rmtree.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter()


PipelineName = Literal["microsoft", "bam"]


# ── Knowledge-source storage ─────────────────────────────────────────────────


def _ms_root(data_root: Path) -> Path:
    """Top-level dir holding Microsoft pipeline knowledge sources.

    Kept separate from local-pdf's ``{slug}/`` tree so a Microsoft
    source can carry the same name as a local-pdf doc without
    colliding, and so listing one set doesn't accidentally show items
    from the other.
    """
    return data_root / "microsoft-sources"


def _src_dir(data_root: Path, slug: str) -> Path:
    return _ms_root(data_root) / slug


# Lowercase, alnum + dash. Mirrors local-pdf.unique_slug but kept local
# so we don't pull from a sibling router.
_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _make_slug(filename: str) -> str:
    base = filename.rsplit(".", 1)[0].lower()
    base = _SLUG_RE.sub("-", base).strip("-")
    return base or "doc"


def _unique_slug(data_root: Path, filename: str) -> str:
    base = _make_slug(filename)
    candidate = base
    n = 2
    while _src_dir(data_root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


# ── Schemas ──────────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    source: str | None = None


class PipelineChunk(BaseModel):
    chunk_id: str
    title: str | None = None
    chunk: str
    score: float
    source_file: str | None = None


class AskResponse(BaseModel):
    pipeline: PipelineName
    question: str
    chunks: list[PipelineChunk]
    answer: str


class KnowledgeSource(BaseModel):
    slug: str
    filename: str
    pages: int
    state: Literal["uploaded", "analyzed", "chunked", "embedded", "indexed", "error"]
    error: str | None = None
    index_name: str | None = None


class PipelineInfo(BaseModel):
    name: str
    label: str
    available: bool
    note: str | None = None


# ── Microsoft pipeline runner (ASK) ──────────────────────────────────────────


def _ask_microsoft(question: str, top_k: int, source: str | None) -> AskResponse:
    """Run hybrid_search + Azure OpenAI completion for one question.

    When *source* is set, scopes the search to that knowledge source's
    Azure index (`kb-{source}`); otherwise falls back to the env-
    configured default index (legacy path).
    """
    try:
        from query_index.client import get_openai_client
        from query_index.config import Config
        from query_index.search import hybrid_search
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Microsoft pipeline package not installed: {exc}",
        ) from exc

    try:
        cfg = Config.from_env()
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Microsoft credentials missing in env: {exc}",
        ) from exc

    # Override the default index name when scoped to a source.
    if source:
        cfg = cfg.model_copy(update={"ai_search_index_name": _index_name_for(source)})

    try:
        hits = hybrid_search(question, top=top_k, cfg=cfg)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Azure search failed: {exc}") from exc

    chunks = [
        PipelineChunk(
            chunk_id=h.chunk_id,
            title=h.title,
            chunk=h.chunk,
            score=h.score,
            source_file=h.source_file,
        )
        for h in hits
    ]

    import os

    chat_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not chat_deployment:
        raise HTTPException(
            status_code=503,
            detail="AZURE_OPENAI_CHAT_DEPLOYMENT not set — can't ask Microsoft for an answer",
        )

    context = "\n\n---\n\n".join(
        f"[{i + 1}] {c.title or c.chunk_id}\n{c.chunk}" for i, c in enumerate(chunks)
    )
    prompt = (
        "Beantworte die Frage AUSSCHLIESSLICH anhand des unten stehenden Kontexts. "
        "Wenn der Kontext die Antwort nicht enthält, antworte mit 'unbekannt'. "
        "Antworte knapp in der Sprache der Frage.\n\n"
        f"Kontext:\n{context}\n\n"
        f"Frage: {question}"
    )

    client = get_openai_client(cfg)
    try:
        resp = client.chat.completions.create(
            model=chat_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Azure chat failed: {exc}") from exc

    answer = (resp.choices[0].message.content or "").strip()
    return AskResponse(pipeline="microsoft", question=question, chunks=chunks, answer=answer)


def _index_name_for(slug: str) -> str:
    """Fresh per-source index name. Azure AI Search requires lowercase
    + alphanumeric/dash + max 128 chars; our slug is already lowercase
    with dashes, so just prefix."""
    return f"kb-{slug}"[:128]


@router.post("/api/admin/pipelines/{name}/ask", response_model=AskResponse)
async def ask(name: str, body: AskRequest) -> AskResponse:
    if name == "microsoft":
        return _ask_microsoft(body.question, body.top_k, body.source)
    if name == "bam":
        raise HTTPException(status_code=501, detail="BAM pipeline not implemented yet")
    raise HTTPException(status_code=404, detail=f"unknown pipeline: {name}")


# ── Microsoft knowledge sources (UPLOAD / LIST / DELETE) ─────────────────────


def _read_source(data_root: Path, slug: str) -> KnowledgeSource | None:
    """Read the per-source meta JSON. Returns None if missing."""
    import json

    d = _src_dir(data_root, slug)
    meta = d / "meta.json"
    if not meta.exists():
        return None
    try:
        raw = json.loads(meta.read_text())
    except Exception:
        return None
    return KnowledgeSource(**raw)


def _write_source(data_root: Path, src: KnowledgeSource) -> None:
    import json

    d = _src_dir(data_root, src.slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(src.model_dump(mode="json"), indent=2))


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Quick page count via pypdf — no rendering, just metadata. Falls
    back to 1 if pypdf can't read the file (corrupt PDFs are rare on
    upload but shouldn't blow up the route)."""
    try:
        from io import BytesIO

        from pypdf import PdfReader

        return len(PdfReader(BytesIO(pdf_bytes)).pages) or 1
    except Exception:
        return 1


@router.post(
    "/api/admin/pipelines/microsoft/sources",
    status_code=201,
    response_model=KnowledgeSource,
)
async def upload_source(request: Request, file: UploadFile) -> KnowledgeSource:
    """Upload a PDF as a Microsoft knowledge source.

    Separate from the local-pdf /api/admin/docs uploader: ingestion
    artifacts (analyze.json, chunks.jsonl, embedded.jsonl) live under
    a parallel ``microsoft-sources/`` tree so the two pipelines never
    cross.
    """
    cfg = request.app.state.config
    filename = file.filename or "untitled.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF uploads accepted")
    blob = await file.read()
    if not blob.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="not a PDF (missing %PDF magic)")

    slug = _unique_slug(cfg.data_root, filename)
    d = _src_dir(cfg.data_root, slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "source.pdf").write_bytes(blob)

    src = KnowledgeSource(
        slug=slug,
        filename=filename,
        pages=_count_pdf_pages(blob),
        state="uploaded",
        error=None,
        index_name=None,
    )
    _write_source(cfg.data_root, src)
    return src


@router.get("/api/admin/pipelines/microsoft/sources", response_model=list[KnowledgeSource])
async def list_sources(request: Request) -> list[KnowledgeSource]:
    cfg = request.app.state.config
    root = _ms_root(cfg.data_root)
    if not root.exists():
        return []
    out: list[KnowledgeSource] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        src = _read_source(cfg.data_root, entry.name)
        if src is not None:
            out.append(src)
    return out


@router.delete(
    "/api/admin/pipelines/microsoft/sources/{slug}",
    status_code=204,
)
async def delete_source(slug: str, request: Request) -> None:
    """Wipe the source's local artifacts AND its Azure index.

    Best-effort on the Azure side — if the index delete fails we
    still drop the local files so the user can re-ingest under the
    same slug.
    """
    import shutil

    cfg = request.app.state.config
    d = _src_dir(cfg.data_root, slug)
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"source not found: {slug}")

    # Try to drop the Azure index first.
    try:
        from query_index.client import get_search_index_client
        from query_index.config import Config

        cfg_az = Config.from_env()
        idx_client = get_search_index_client(cfg_az)
        idx_client.delete_index(_index_name_for(slug))
    except Exception:
        # Either the index never got created or Azure call failed —
        # not fatal. Local files still wipe so the user can retry.
        pass

    shutil.rmtree(d, ignore_errors=True)


# ── Pipelines list ───────────────────────────────────────────────────────────


@router.get("/api/admin/pipelines", response_model=list[PipelineInfo])
async def list_pipelines() -> list[PipelineInfo]:
    import os

    ms_keys_present = bool(
        os.environ.get("AI_SEARCH_KEY")
        and os.environ.get("AI_SEARCH_ENDPOINT")
        and os.environ.get("AI_SEARCH_INDEX_NAME")
    )
    return [
        PipelineInfo(
            name="microsoft",
            label="Microsoft",
            available=ms_keys_present,
            note=None if ms_keys_present else "Azure-Credentials fehlen in .env",
        ),
        PipelineInfo(
            name="bam",
            label="BAM",
            available=False,
            note="Noch nicht implementiert",
        ),
    ]


# Mypy quiet-down for unused TYPE_CHECKING import slot.
_: Any = None
