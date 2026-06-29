# Provenienz Schritt für Schritt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A second mode in the Agent tab — a **claim-verification provenance agent** (Azure GPT-4.1) that, given a stated value (e.g. *"die Gesamtwärmeleistung von 4,056 kW"*), traces it **step by step**, streaming one structured step-card at a time, and ends with a verdict (KORREKT / NICHT KORREKT / NICHT BELEGBAR) + the quoted source.

**Architecture:** Fully **additive** to the working research spike (tag `agent-spike-research-v1`) — nothing in the research path changes. A new **flat** `build_verifier_agent()` (no sub-agents, so every step streams from the main loop, unlike the research agent which hides work in a sub-agent), a new `record_step` tool whose call-arguments ARE the streamed step content, a German provenance-methodology prompt, a new endpoint `POST /api/admin/agent/verify`, and a second panel in `Agent.tsx`.

**Tech Stack:** existing — `deepagents==0.6.11` + `langchain-openai` (Azure GPT-4.1), `query_index.hybrid_search`, FastAPI NDJSON `StreamingResponse`, React.

**Verification semantics:** checks **traceability + value-match against the quoted source**, NOT recalculation. The document carries several related figures (the research run surfaced 5,597 kW conservative vs 4,056 kW actual TRINO), so the agent must state WHICH value it matched and quote the exact source sentence.

**Scope guard — OUT:** interactive pause/resume between steps (this build is autonomous-streaming); recalculation/arithmetic checking; slug-scoped retrieval; touching the research `/ask` path, `azure_ai_search`, `build_agent`, or the research prompts.

**Additive-only file touch list:**
- Create: `agent/verify_prompts.py`, and ADD to `agent/tools.py` (a `record_step` tool — `azure_ai_search`/`think_tool` untouched), ADD `build_verifier_agent()` + `_build_model()` to `agent/build.py` (`build_agent` untouched), ADD export to `agent/__init__.py`, ADD a `/verify` route to `api/routers/admin/agent.py` (the `/ask` route untouched), ADD a second panel to `frontend/src/admin/routes/Agent.tsx`.

---

## Task 1: Verifier agent (prompt + record_step tool + flat builder) + true/false smoke gate

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/agent/verify_prompts.py`
- Modify: `agent/tools.py` (add `record_step`), `agent/build.py` (add `_build_model` + `build_verifier_agent`), `agent/__init__.py` (export)

- [x] **Step 1: Create the provenance-verification prompt**

`features/pipelines/local-pdf/src/local_pdf/agent/verify_prompts.py`:

```python
# ruff: noqa: E501 — German prompt prose; long lines are intentional.
"""System prompt for the step-by-step Provenienz verification agent."""

PROVENANZ_VERIFY = """Du bist ein Provenienz-Prüfer für ein technisches Dokument (Brennelement-Transport-/Lagerbehälter). Heutiges Datum: {date}.

<Aufgabe>
Du prüfst, ob eine angegebene Behauptung — typischerweise ein Zahlenwert wie „die Gesamtwärmeleistung von X kW" — im indizierten Dokument BELEGBAR ist und mit der Quelle ÜBEREINSTIMMT. Du rechnest NICHTS nach. Du prüfst: Verortung (wo steht der Wert?), Provenienz (ist das die Quelle oder ein Verweis?) und Werte-Übereinstimmung gegen das wörtliche Quellenzitat.
</Aufgabe>

<Werkzeuge>
1. azure_ai_search(query, top): durchsucht den Dokument-Index (deutsch).
2. record_step(nr, frage, aktion, befund, zwischenfazit, quelle): protokolliert EINEN Prüfschritt. Rufe es nach JEDER Such-/Untersuchungs-Aktion auf, BEVOR du weitermachst — so wird die Prüfung Schritt für Schritt sichtbar. `quelle` nur ausfüllen, wenn du in diesem Schritt einen wörtlichen Quellenbeleg gefunden hast.
3. write_file: schreibe dein Endurteil nach `/urteil.md` (siehe <Abschluss>).
</Werkzeuge>

<Methodik — arbeite diese Schritte der Reihe nach ab und protokolliere JEDEN mit record_step>
1. Verorten: Wo im Dokument wird dieser Wert genannt? Suche gezielt danach.
2. Referenz prüfen: Gibt es an der Fundstelle eine Quellenangabe/einen Verweis (z.B. „[3]", „in den Berechnungen", „siehe Abschnitt …")?
3. Quelle bestimmen: Ist die gefundene Stelle die QUELLE des Werts — oder nur eine wiederholende/abgeleitete Erwähnung, die weiterverweist?
4. Zur Quelle verfolgen: Folge den Verweisen bis zum Ursprungssatz. Ein typischer Ursprungssatz hat die Form: „In den Berechnungen werden nur Brennelemente (BE) des Typs TRINO mit einer Gesamtwärmeleistung von … kW berücksichtigt. Die Brennelemente des Typs Garigliano sind durch diese Berechnungen mit abgedeckt."
5. Urteil: Stimmt der angegebene Wert mit dem Wert in der Quelle überein?
</Methodik>

<Wichtig>
- Das Dokument enthält MEHRERE verwandte Werte (z.B. ein konservativ angesetzter Wert vs. der tatsächliche Maximalwert). Nenne IMMER, WELCHEN Wert du gematcht hast, und zitiere den Quellensatz WÖRTLICH samt Abschnitt.
- Stimmt der angegebene Wert NICHT mit der Quelle überein: sage das klar und nenne den tatsächlichen Wert aus der Quelle.
- Ist der Wert gar nicht auffindbar: sage das klar (NICHT BELEGBAR). Erfinde nichts.
</Wichtig>

<Grenzen>
- Höchstens etwa 6 Suchaufrufe. Stoppe, sobald die Quellenkette belegt — oder als nicht belegbar erwiesen — ist.
</Grenzen>

<Abschluss>
Schreibe zum Schluss mit write_file nach `/urteil.md` ein kurzes Urteil mit:
(a) **Ergebnis:** KORREKT / NICHT KORREKT / NICHT BELEGBAR
(b) **Gematchter Wert + Quelle:** der Wert aus der Quelle, der Abschnitt und das WÖRTLICHE Quellenzitat
(c) **Begründung:** ein bis zwei Sätze.
</Abschluss>
"""
```

- [x] **Step 2: Add the `record_step` tool to `agent/tools.py`** (append; do NOT change `azure_ai_search`/`think_tool`)

Append to `features/pipelines/local-pdf/src/local_pdf/agent/tools.py`:

```python


@tool(parse_docstring=True)
def record_step(
    nr: int,
    frage: str,
    aktion: str,
    befund: str,
    zwischenfazit: str,
    quelle: str = "",
) -> str:
    """Protokolliere EINEN Schritt der Provenienz-Prüfung. Nach jeder Untersuchungs-Aktion aufrufen, bevor du weitermachst.

    Args:
        nr: Schrittnummer (1, 2, 3, ...).
        frage: Die Leitfrage dieses Schritts (z.B. "Wo wird dieser Wert genannt?").
        aktion: Was du getan hast (z.B. "Index nach 'Gesamtwärmeleistung TRINO' durchsucht").
        befund: Was du gefunden hast — kurz, mit konkreten Werten/Abschnitten.
        zwischenfazit: Deine Schlussfolgerung aus diesem Schritt.
        quelle: Optionaler wörtlicher Quellenbeleg (Abschnitt + Zitat), falls in diesem Schritt gefunden.

    Returns:
        Bestätigung, dass der Schritt protokolliert wurde.
    """
    return f"Schritt {nr} protokolliert."
```

- [x] **Step 3: Add `_build_model()` + `build_verifier_agent()` to `agent/build.py`** (append; do NOT change `build_agent`)

Append to `features/pipelines/local-pdf/src/local_pdf/agent/build.py`:

```python


def _build_model():
    """Azure GPT-4.1 chat model from our AI_FOUNDRY_* env (shared by the verifier)."""
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        azure_deployment=os.environ["CHAT_DEPLOYMENT_NAME"],
        api_key=os.environ["AI_FOUNDRY_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        temperature=0.0,
    )


def build_verifier_agent():
    """Flat (no sub-agents) step-by-step provenance verifier. Requires the `agent` extra.

    Flat on purpose: every step streams from the main loop instead of being hidden in a
    delegated sub-agent (the opposite of the research agent's design).
    """
    from deepagents import create_deep_agent

    from local_pdf.agent.tools import azure_ai_search, record_step
    from local_pdf.agent.verify_prompts import PROVENANZ_VERIFY

    current_date = datetime.now().strftime("%Y-%m-%d")
    return create_deep_agent(
        model=_build_model(),
        tools=[azure_ai_search, record_step],
        system_prompt=PROVENANZ_VERIFY.format(date=current_date),
    )
```

- [x] **Step 4: Export `build_verifier_agent` from `agent/__init__.py`**

Change the `__init__.py` to also export the verifier (keep `build_agent`):

```python
"""Self-contained deepagents agents (Azure GPT-4.1 + AI Search) for the Agent tab spike."""

from local_pdf.agent.build import build_agent, build_verifier_agent

__all__ = ["build_agent", "build_verifier_agent"]
```

- [x] **Step 5: Standalone smoke — TRUE and FALSE claim (the go/no-go gate)**

Run the verifier on a value that IS in the document and one that is NOT. This is the gate: a verifier that says KORREKT for a wrong number is worse than useless.

```bash
source .venv/bin/activate
set -a; source .env; set +a
python - <<'PY'
import asyncio
from local_pdf.agent import build_verifier_agent
from deepagents.backends.utils import file_data_to_string

async def verify(claim):
    agent = build_verifier_agent()
    files, steps = {}, []
    async for ns, chunk in agent.astream(
        {"messages": [{"role": "user", "content": f"Prüfe folgende Behauptung: {claim}"}]},
        stream_mode="updates", subgraphs=True,
    ):
        if not ns and isinstance(chunk, dict):
            for out in chunk.values():
                if isinstance(out, dict) and "files" in out:
                    files.update(out["files"])
        if isinstance(chunk, dict):
            for out in chunk.values():
                if not isinstance(out, dict):
                    continue
                for msg in out.get("messages", []):
                    for tc in getattr(msg, "tool_calls", None) or []:
                        if tc.get("name") == "record_step":
                            steps.append(tc.get("args", {}))
    print(f"\n######## CLAIM: {claim}")
    for s in steps:
        print(f"  [Schritt {s.get('nr')}] {s.get('frage')}\n      Befund: {s.get('befund')}\n      Fazit: {s.get('zwischenfazit')}\n      Quelle: {s.get('quelle','')[:160]}")
    print("  ===== URTEIL =====")
    print("  " + (file_data_to_string(files["/urteil.md"]) if "/urteil.md" in files else "(kein /urteil.md)").replace("\n", "\n  "))

async def main():
    await verify("Die Gesamtwärmeleistung der TRINO-Beladung beträgt 4,056 kW.")   # plausibly TRUE (in doc)
    await verify("Die Gesamtwärmeleistung beträgt 12,5 kW.")                       # FALSE (not in doc)

asyncio.run(main())
PY
```

**Go/no-go gate:** The TRUE claim must stream coherent steps and end with a verdict that quotes the source sentence and states the matched value. The FALSE claim must end **NICHT KORREKT** (or NICHT BELEGBAR) and surface the real value — it must NOT rubber-stamp the wrong number. If the false case passes as KORREKT, STOP and report; the prompt/tools need work before wiring the UI. (Final domain sign-off on the true value is the user's.)

- [x] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/agent/
git commit -m "feat(agent): step-by-step provenance verifier agent (flat deepagents)"
```

---

## Task 2: `/api/admin/agent/verify` streaming endpoint

**Files:** Modify `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py` (ADD a route; leave `/ask` untouched)

- [x] **Step 1: Append the verify endpoint** to `agent.py`

Add a request model near `AgentAskBody`:

```python
class AgentVerifyBody(BaseModel):
    claim: str
```

Append the route (mirrors `/ask`, but streams `record_step` args as `step` events and reads `/urteil.md` as the verdict):

```python
@router.post("/api/admin/agent/verify")
async def agent_verify(body: AgentVerifyBody, request: Request) -> StreamingResponse:
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent import build_verifier_agent  # lazy

    agent = build_verifier_agent()

    async def _stream():
        files: dict = {}
        try:
            async for ns, chunk in agent.astream(
                {"messages": [{"role": "user", "content": f"Prüfe folgende Behauptung: {body.claim}"}]},
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
                                    yield json.dumps(
                                        {"event": "step", **(tc.get("args") or {})},
                                        ensure_ascii=False,
                                    ) + "\n"
                await asyncio.sleep(0)

            verdict = file_data_to_string(files["/urteil.md"]) if "/urteil.md" in files else ""
            yield json.dumps({"event": "verdict", "markdown": verdict}, ensure_ascii=False) + "\n"
            yield json.dumps({"event": "done"}) + "\n"
        except Exception as exc:
            yield json.dumps({"event": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
```

- [x] **Step 2: Import check** (no server needed)

```bash
source .venv/bin/activate
python -c "from local_pdf.api.app import create_app; create_app(); print('create_app OK')"
```

Expected: OK (route added; deepagents still lazy).

- [x] **Step 3: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py
git commit -m "feat(agent): /api/admin/agent/verify step-by-step NDJSON endpoint"
```

(Live curl deferred to controller end-to-end, like Task 4 of the research plan.)

---

## Task 3: Frontend — second panel "Provenienz Schritt für Schritt"

**Files:** Modify `frontend/src/admin/routes/Agent.tsx` (ADD a second panel below the existing research panel; do NOT remove/restructure the research panel)

- [x] **Step 1: Add verifier state + a `runVerify` streamer + the panel**

In `Agent.tsx`, add alongside the existing research state:

```tsx
  type Step = { nr?: number; frage?: string; aktion?: string; befund?: string; zwischenfazit?: string; quelle?: string };
  const [claim, setClaim] = useState("Die Gesamtwärmeleistung der TRINO-Beladung beträgt 4,056 kW.");
  const [steps, setSteps] = useState<Step[]>([]);
  const [verdict, setVerdict] = useState("");
  const [verifying, setVerifying] = useState(false);
  const verifyAbort = useRef<AbortController | null>(null);

  async function runVerify() {
    setSteps([]); setVerdict(""); setError(null); setVerifying(true);
    const ctrl = new AbortController();
    verifyAbort.current = ctrl;
    try {
      const r = await fetch(`${apiBase()}/api/admin/agent/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token ?? "" },
        body: JSON.stringify({ claim }),
        signal: ctrl.signal,
      });
      if (!r.body) throw new Error("no response body");
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl = buf.indexOf("\n");
        while (nl !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line) {
            const ev = JSON.parse(line);
            if (ev.event === "step") setSteps((s) => [...s, ev as Step]);
            else if (ev.event === "verdict") setVerdict(ev.markdown);
            else if (ev.event === "error") setError(ev.detail);
          }
          nl = buf.indexOf("\n");
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(String(e));
    } finally {
      setVerifying(false);
      verifyAbort.current = null;
    }
  }
```

Add the panel JSX below the existing research block (inside the same scrolling `<div className="p-6 ...">`, after the research `{report && ...}`):

```tsx
        <hr className="border-line my-2" />
        <div className="space-y-3">
          <h3 className="text-[14px] font-semibold text-bam-navy">Provenienz Schritt für Schritt</h3>
          <input
            className="w-full border border-line rounded p-2 text-[13px]"
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            placeholder="z.B. Die Gesamtwärmeleistung von 4,056 kW"
          />
          <div className="flex gap-2">
            <button className="btn-primary" onClick={runVerify} disabled={verifying || !claim.trim()}>
              {verifying ? "Prüft…" : "Provenienz Schritt für Schritt"}
            </button>
            {verifying && (
              <button className="btn-secondary" onClick={() => verifyAbort.current?.abort()}>Abbrechen</button>
            )}
          </div>
          {steps.length > 0 && (
            <ol className="space-y-2">
              {steps.map((s, i) => (
                <li key={i} className="border border-line rounded p-3 text-[13px] bg-white">
                  <div className="font-semibold text-bam-navy">Schritt {s.nr ?? i + 1}: {s.frage}</div>
                  {s.aktion && <div className="text-ink-muted mt-1"><span className="font-medium">Aktion:</span> {s.aktion}</div>}
                  {s.befund && <div className="mt-1"><span className="font-medium">Befund:</span> {s.befund}</div>}
                  {s.zwischenfazit && <div className="mt-1"><span className="font-medium">Fazit:</span> {s.zwischenfazit}</div>}
                  {s.quelle && <div className="mt-1 text-ink-muted italic">Quelle: {s.quelle}</div>}
                </li>
              ))}
            </ol>
          )}
          {verdict && (
            <pre className="whitespace-pre-wrap text-[13px] bg-cyan-50 border border-bam-cyan rounded p-4">{verdict}</pre>
          )}
        </div>
```

(If `bam-cyan`/`bam-navy`/`ink-muted`/`border-line` tokens differ, mirror what the existing research block / sibling pages use. The research panel above is left exactly as-is.)

- [x] **Step 2: Build**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: exit 0.

- [x] **Step 3: Commit**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/routes/Agent.tsx
git commit -m "feat(agent): Provenienz Schritt für Schritt panel (streamed step cards + verdict)"
```

---

## Task 4: End-to-end (true + false) + verify the research path still works

**Files:** none (controller verification)

- [ ] **Step 1: Live endpoint test on a throwaway port** (controller; does not disturb the user's :8001)

Boot `query-eval segment serve --port 8011`, then POST `/api/admin/agent/verify` with the TRUE claim and the FALSE claim; confirm each streams `step` events then a `verdict`, and that the FALSE claim's verdict is NICHT KORREKT / NICHT BELEGBAR (not a rubber-stamp). Tear the server down.

- [ ] **Step 2: Confirm the research path is untouched** — POST `/api/admin/agent/ask` once on the same throwaway server; it must still stream a `report` (the tag-protected baseline still works).

- [ ] **Step 3: Surface both verdicts to the user** for the domain correctness sign-off (the real-number check), and the in-browser try (restart :8001 → Agent tab → second panel).

---

## Self-Review (author)

- **Additive:** every change is an append or a new file; `build_agent`, `azure_ai_search`, the research prompts, and the `/ask` route are byte-unchanged → `agent-spike-research-v1` behavior preserved (Task 4 Step 2 proves it).
- **Flat agent:** `build_verifier_agent` passes no `subagents` → steps stream from the main loop (the whole point).
- **Step content streamed, not tool names:** the endpoint emits `record_step` *arguments* as `{event:"step",…}`.
- **Gate is true+false:** Task 1 Step 5 + Task 4 Step 1 both require the FALSE value to be caught.
- **Placeholder scan:** none — full code given for every file; prompt is complete German.
- **Boundary/lint:** `tools.py` adds no `openai`/`azure.search` import (still only `langchain_core.tools` + `query_index`); `verify_prompts.py` carries `# ruff: noqa: E501` like the vendor prompts; reflow any >100-char Python in `build.py`/endpoint before commit.
- **Residual risk:** the agent must remember to `write_file('/urteil.md')`; if it doesn't, the verdict event is empty — the prompt's `<Abschluss>` makes it explicit, and GPT-4.1 follows it reliably (acceptable for a spike; the steps still stream regardless).
