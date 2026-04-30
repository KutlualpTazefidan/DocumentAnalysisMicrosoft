"""LLM-driven synthetic goldset generator.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tiktoken
from llm_clients.base import Message, ResponseFormat

from goldens.creation.prompts import load_prompt
from goldens.creation.synthetic_decomposition import decompose_to_sub_units
from goldens.creation.synthetic_dedup import QuestionDedup
from goldens.operations._time import now_utc_iso
from goldens.schemas.base import Event, LLMActor, SourceElement
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, read_events

if TYPE_CHECKING:
    import argparse

    from llm_clients.base import LLMClient

    from goldens.creation._elements_stub import DocumentElement, ElementsLoader

__all__ = [
    "GeneratedQuestion",
    "SynthesiseResult",
    "cmd_synthesise",
    "synthesise",
]

_log = logging.getLogger(__name__)


# ---------- Result types --------------------------------------------


@dataclass(frozen=True)
class GeneratedQuestion:
    sub_unit: str
    question: str


@dataclass(frozen=True)
class SynthesiseResult:
    slug: str
    events_path: Path
    elements_seen: int
    elements_skipped: int
    elements_with_questions: int
    questions_generated: int
    questions_kept: int
    questions_dropped_dedup: int
    questions_dropped_cap: int
    events_written: int
    prompt_tokens_estimated: int
    dry_run: bool


# ---------- Internals -----------------------------------------------


def _render_prompt(template: str, sub_units: tuple[str, ...]) -> str:
    """Render the bundled prompt: serialise the indexed sub-units into
    `{content}`."""
    indexed = "\n".join(f"{i}. {s}" for i, s in enumerate(sub_units))
    return template.format(content=indexed)


def _parse_questions(raw: str) -> list[GeneratedQuestion] | None:
    """Parse the LLM JSON response. Returns None on JSONDecodeError or
    on shape that is not `{questions: [...]}`. Otherwise returns the
    list of (validated) GeneratedQuestion objects."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[GeneratedQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            _log.warning("dropping non-object item in questions list: %r", item)
            continue
        sub_unit = item.get("sub_unit")
        question = item.get("question")
        if not isinstance(sub_unit, str) or not isinstance(question, str):
            _log.warning("dropping item missing sub_unit/question: %r", item)
            continue
        if not question.strip():
            _log.warning("dropping item with empty question: %r", item)
            continue
        out.append(GeneratedQuestion(sub_unit=sub_unit, question=question))
    return out


def _generate_question_batches(
    element: DocumentElement,
    sub_units: tuple[str, ...],
    *,
    client: LLMClient,
    model: str,
    template: str,
    temperature: float,
    max_prompt_tokens: int,
    tokenizer: tiktoken.Encoding,
) -> tuple[list[GeneratedQuestion], str | None, int]:
    """Drive one element through the LLM. Returns
    `(questions, resolved_model_version, tokens_estimated)` — a flat
    list of all questions generated for this element regardless of
    bundled vs. per-sub-unit mode. The caller runs a single dedup pass
    over the union, scoped per element (`source_key=bare_id`), so
    bundled and fallback modes are semantically equivalent w.r.t.
    dedup scope.

    Strategy (spec §4.3):
      1. Build the bundled prompt; estimate tokens with tiktoken.
      2. If estimated > max_prompt_tokens → fallback to per-sub-unit calls.
      3. Else: 1 JSON-mode call. On JSONDecodeError, retry once.
         Second failure → log + skip (return [], None, tokens).
    """
    bundled = _render_prompt(template, sub_units)
    bundled_tokens = len(tokenizer.encode(bundled))

    if bundled_tokens > max_prompt_tokens:
        _log.info(
            "element %s: bundled prompt %d tokens > %d; falling back to per-sub-unit calls",
            element.element_id,
            bundled_tokens,
            max_prompt_tokens,
        )
        all_qs: list[GeneratedQuestion] = []
        resolved = None
        total_tokens = 0
        for i, s in enumerate(sub_units):
            single = _render_prompt(template, (s,))
            total_tokens += len(tokenizer.encode(single))
            qs, model_version = _one_call(
                client=client,
                model=model,
                prompt=single,
                temperature=temperature,
            )
            if qs is None:
                _log.warning(
                    "skipping element %s sub-unit %d after JSON parse failures",
                    element.element_id,
                    i,
                )
                continue
            resolved = resolved or model_version
            all_qs.extend(qs)
        return all_qs, resolved, total_tokens

    qs, model_version = _one_call(
        client=client, model=model, prompt=bundled, temperature=temperature
    )
    if qs is None:
        _log.warning("skipping element %s after JSON parse failures", element.element_id)
        return [], None, bundled_tokens
    return qs, model_version, bundled_tokens


def _one_call(
    *,
    client: LLMClient,
    model: str,
    prompt: str,
    temperature: float,
) -> tuple[list[GeneratedQuestion] | None, str | None]:
    """One JSON-mode completion with one retry on parse failure.
    Returns (questions, resolved_model_version) or (None, None) on
    two consecutive parse failures."""
    messages = [Message(role="user", content=prompt)]
    rf = ResponseFormat(type="json_object")
    for _attempt in range(2):
        completion = client.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=rf,
        )
        parsed = _parse_questions(completion.text)
        if parsed is not None:
            return parsed, completion.model
    return None, None


def _build_event(
    *,
    slug: str,
    element: DocumentElement,
    question: str,
    actor: LLMActor,
    timestamp_utc: str,
) -> Event:
    # Strip the "p{page}-" prefix so the persisted element_id is the
    # bare 8-char content hash (matches A.4's loader.to_source_element
    # mapping; spec §4.5).
    bare_element_id = element.element_id.split("-", 1)[1]
    src = SourceElement(
        document_id=slug,
        page_number=element.page_number,
        element_id=bare_element_id,
        element_type=element.element_type,
    )
    return Event(
        event_id=new_event_id(),
        timestamp_utc=timestamp_utc,
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor.to_dict(),
            "action": "synthesised",
            "notes": None,
            "entry_data": {
                "query": question,
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "refines": None,
                "source_element": src.to_dict(),
            },
        },
    )


def _existing_questions_for(events_path: Path, bare_element_id: str) -> list[str]:
    """Return queries from existing `created`+retrieval events whose
    persisted `entry_data.source_element.element_id` equals
    `bare_element_id`. Used by dedup to compare new generations against
    questions already on disk for the same source element."""
    if not events_path.exists():
        return []
    out: list[str] = []
    for ev in read_events(events_path):
        if ev.event_type != "created":
            continue
        entry_data = ev.payload.get("entry_data") or {}
        if ev.payload.get("task_type") != "retrieval":
            continue
        src = entry_data.get("source_element")
        if not isinstance(src, dict):
            continue
        if src.get("element_id") != bare_element_id:
            continue
        q = entry_data.get("query")
        if isinstance(q, str) and q:
            out.append(q)
    return out


def _resolve_template_for(element: DocumentElement, version: str) -> str | None:
    """Resolve the prompt template for this element's type. Returns
    None for element_types that are skipped in v1 (heading, figure)
    or have no shipped template."""
    et = element.element_type
    if et == "table":
        template: str = load_prompt("table_row", version)
        return template
    if et in ("paragraph", "list_item"):
        template = load_prompt(et, version)
        return template
    return None  # heading / figure


# ---------- Driver --------------------------------------------------


def synthesise(
    *,
    slug: str,
    loader: ElementsLoader,
    client: LLMClient,
    embed_client: LLMClient | None,
    model: str,
    embedding_model: str | None,
    prompt_template_version: str = "v1",
    temperature: float = 0.0,
    max_questions_per_element: int = 20,
    max_prompt_tokens: int = 8000,
    start_from: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
    events_path: Path | None = None,
) -> SynthesiseResult:
    """Walk loader.elements(), generate questions, write events.
    See spec §4.5 for the full flow."""
    events_path = events_path or (Path("outputs") / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME)

    existing_keys: set[str] = set()
    if resume and events_path.exists():
        for ev in read_events(events_path):
            if ev.event_type != "created":
                continue
            entry_data = ev.payload.get("entry_data") or {}
            src = entry_data.get("source_element")
            if isinstance(src, dict):
                eid = src.get("element_id")
                if isinstance(eid, str):
                    existing_keys.add(eid)

    tokenizer = tiktoken.get_encoding("cl100k_base")
    dedup = QuestionDedup(
        client=embed_client,
        model=embedding_model or "",
        threshold=0.95,
    )

    elements_seen = 0
    elements_skipped = 0
    elements_with_questions = 0
    questions_generated = 0
    questions_kept = 0
    questions_dropped_cap = 0
    events_written = 0
    prompt_tokens_estimated = 0

    started = start_from is None
    yielded = 0

    for element in loader.elements():
        if not started:
            if element.element_id == start_from:
                started = True
            else:
                continue
        if limit is not None and yielded >= limit:
            break
        yielded += 1
        elements_seen += 1

        # Resume skip uses the BARE hash (matches what we persist).
        bare_id = element.element_id.split("-", 1)[1]
        if resume and bare_id in existing_keys:
            elements_skipped += 1
            continue

        sub_units = decompose_to_sub_units(element)
        if not sub_units:
            elements_skipped += 1
            continue

        template = _resolve_template_for(element, prompt_template_version)
        if template is None:
            elements_skipped += 1
            continue

        # Dry-run short-circuit BEFORE any LLM call (completion or embedding).
        if dry_run:
            rendered = _render_prompt(template, sub_units)
            prompt_tokens_estimated += len(tokenizer.encode(rendered))
            continue

        existing_questions = _existing_questions_for(events_path, bare_id)

        generated, model_version, tokens = _generate_question_batches(
            element,
            sub_units,
            client=client,
            model=model,
            template=template,
            temperature=temperature,
            max_prompt_tokens=max_prompt_tokens,
            tokenizer=tokenizer,
        )
        prompt_tokens_estimated += tokens
        questions_generated += len(generated)
        if not generated:
            elements_skipped += 1
            continue

        kept = dedup.filter(
            [g.question for g in generated],
            against=existing_questions,
            source_key=bare_id,
        )
        kept_set = set(kept)
        kept_objs: list[GeneratedQuestion] = [g for g in generated if g.question in kept_set]

        if len(kept_objs) > max_questions_per_element:
            dropped = len(kept_objs) - max_questions_per_element
            questions_dropped_cap += dropped
            _log.warning(
                "element %s: %d kept questions exceeds cap %d; truncating",
                element.element_id,
                len(kept_objs),
                max_questions_per_element,
            )
            kept_objs = kept_objs[:max_questions_per_element]

        if not kept_objs:
            elements_skipped += 1
            continue

        elements_with_questions += 1
        ts = now_utc_iso()
        actor = LLMActor(
            model=model,
            model_version=model_version or model,
            prompt_template_version=prompt_template_version,
            temperature=temperature,
        )
        for g in kept_objs:
            ev = _build_event(
                slug=slug,
                element=element,
                question=g.question,
                actor=actor,
                timestamp_utc=ts,
            )
            append_event(events_path, ev)
            events_written += 1
            questions_kept += 1

    questions_dropped_dedup = questions_generated - questions_kept - questions_dropped_cap
    return SynthesiseResult(
        slug=slug,
        events_path=events_path,
        elements_seen=elements_seen,
        elements_skipped=elements_skipped,
        elements_with_questions=elements_with_questions,
        questions_generated=questions_generated,
        questions_kept=questions_kept,
        questions_dropped_dedup=max(questions_dropped_dedup, 0),
        questions_dropped_cap=questions_dropped_cap,
        events_written=events_written,
        prompt_tokens_estimated=prompt_tokens_estimated,
        dry_run=dry_run,
    )


# ---------- CLI handler ---------------------------------------------


def cmd_synthesise(args: argparse.Namespace) -> int:  # pragma: no cover
    """Argparse handler. Builds the LLMClient + embed_client from env
    + flags, instantiates AnalyzeJsonLoader(slug=args.doc) (after A.4
    merges; until then this CLI handler is unreachable in tests and
    marked pragma: no cover), and calls synthesise(...).

    Returns 0 on success, 2 on missing inputs, 1 on unhandled
    exception (logged via logging).
    """
    from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("ERROR: LLM_API_KEY env var is required", flush=True)
        return 2

    base_url = args.llm_base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model = args.llm_model or os.environ.get("LLM_MODEL")
    if not model:
        print("ERROR: --llm-model or LLM_MODEL env var is required", flush=True)
        return 2

    completion_client = OpenAIDirectClient(OpenAIDirectConfig(api_key=api_key, base_url=base_url))

    embed_client: OpenAIDirectClient | None = None
    embedding_model = args.embedding_model or os.environ.get("LLM_EMBEDDING_MODEL")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if embedding_model and openai_key:
        embed_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1")
        )
    elif openai_key and not embedding_model:
        embedding_model = "text-embedding-3-large"
        embed_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1")
        )

    # Loader resolution depends on A.4 — until that lands the CLI
    # handler cannot construct AnalyzeJsonLoader. The synthesise()
    # function is fully usable from Python without going through the
    # CLI; that is what is exercised in tests.
    from goldens.creation.elements import AnalyzeJsonLoader

    loader = AnalyzeJsonLoader(slug=args.doc)

    result = synthesise(
        slug=args.doc,
        loader=loader,
        client=completion_client,
        embed_client=embed_client,
        model=model,
        embedding_model=embedding_model,
        prompt_template_version=args.prompt_template_version,
        temperature=args.temperature,
        max_questions_per_element=args.max_questions_per_element,
        max_prompt_tokens=args.max_prompt_tokens,
        start_from=args.start_from,
        limit=args.limit,
        dry_run=args.dry_run,
        resume=args.resume,
    )
    print(
        f"slug={result.slug} events_written={result.events_written} "
        f"kept={result.questions_kept} dropped_dedup={result.questions_dropped_dedup} "
        f"dropped_cap={result.questions_dropped_cap} "
        f"prompt_tokens_estimated={result.prompt_tokens_estimated} "
        f"dry_run={result.dry_run}"
    )
    return 0
