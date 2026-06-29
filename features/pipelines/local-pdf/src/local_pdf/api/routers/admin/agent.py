"""Agent spike endpoint: drives the deepagents research agent and streams NDJSON.

Mounted under /api/admin/ so it inherits admin auth from the ASGI middleware.
deepagents is imported lazily inside the handler so this router (and the app) import
fine even when the optional `agent` extra is not installed."""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class AgentAskBody(BaseModel):
    question: str


class AgentVerifyBody(BaseModel):
    claim: str


@router.post("/api/admin/agent/ask")
async def agent_ask(body: AgentAskBody, request: Request) -> StreamingResponse:
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent import build_agent  # lazy

    agent = build_agent()

    async def _stream():
        files: dict = {}
        try:
            async for ns, chunk in agent.astream(
                {"messages": [{"role": "user", "content": body.question}]},
                stream_mode="updates",
                subgraphs=True,
            ):
                if await request.is_disconnected():
                    yield json.dumps({"event": "cancelled"}) + "\n"
                    return
                scope = " > ".join(ns) if ns else "orchestrator"
                if isinstance(chunk, dict):
                    for node_output in chunk.values():
                        if not isinstance(node_output, dict):
                            continue
                        if not ns and "files" in node_output:
                            files.update(node_output["files"])
                        for msg in node_output.get("messages", []):
                            for tc in getattr(msg, "tool_calls", None) or []:
                                yield (
                                    json.dumps(
                                        {
                                            "event": "tool",
                                            "scope": scope,
                                            "name": tc.get("name", "?"),
                                        },
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                )
                await asyncio.sleep(0)  # let the loop observe disconnects

            report = (
                file_data_to_string(files["/final_report.md"])
                if "/final_report.md" in files
                else ""
            )
            yield json.dumps({"event": "report", "markdown": report}, ensure_ascii=False) + "\n"
            yield json.dumps({"event": "done"}) + "\n"
        except Exception as exc:  # surface failures to the UI instead of a dead stream
            yield json.dumps({"event": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.post("/api/admin/agent/verify")
async def agent_verify(body: AgentVerifyBody, request: Request) -> StreamingResponse:
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent import build_verifier_agent  # lazy

    agent = build_verifier_agent()

    async def _stream():
        files: dict = {}
        try:
            async for ns, chunk in agent.astream(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Prüfe folgende Behauptung: {body.claim}",
                        }
                    ]
                },
                stream_mode="updates",
                subgraphs=True,
            ):
                if await request.is_disconnected():
                    yield json.dumps({"event": "cancelled"}) + "\n"
                    return
                if isinstance(chunk, dict):
                    for node_output in chunk.values():
                        if not isinstance(node_output, dict):
                            continue
                        if not ns and "files" in node_output:
                            files.update(node_output["files"])
                        for msg in node_output.get("messages", []):
                            for tc in getattr(msg, "tool_calls", None) or []:
                                if tc.get("name") == "record_step":
                                    yield (
                                        json.dumps(
                                            {"event": "step", **(tc.get("args") or {})},
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                await asyncio.sleep(0)

            verdict = file_data_to_string(files["/urteil.md"]) if "/urteil.md" in files else ""
            yield json.dumps({"event": "verdict", "markdown": verdict}, ensure_ascii=False) + "\n"
            yield json.dumps({"event": "done"}) + "\n"
        except Exception as exc:
            yield json.dumps({"event": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
