import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";
import { apiBase } from "../api/adminClient";

type ToolEvent = { scope: string; name: string };

export function Agent(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const [question, setQuestion] = useState(
    "Was ist die Gesamtwärmeleistung und wie wurde sie berechnet? Erkläre jeden Schritt mit Quellenangabe.",
  );
  const [events, setEvents] = useState<ToolEvent[]>([]);
  const [report, setReport] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function run() {
    setEvents([]); setReport(""); setError(null); setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["X-Auth-Token"] = token;
      const r = await fetch(`${apiBase()}/api/admin/agent/ask`, {
        method: "POST",
        headers,
        body: JSON.stringify({ question }),
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
            if (ev.event === "tool") setEvents((e) => [...e, { scope: ev.scope, name: ev.name }]);
            else if (ev.event === "report") setReport(ev.markdown);
            else if (ev.event === "error") setError(ev.detail);
          }
          nl = buf.indexOf("\n");
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(String(e));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-4 py-2 bg-white flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>
      <div className="p-6 overflow-auto space-y-4">
        <textarea
          className="w-full border border-line rounded p-2 text-[13px]"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <div className="flex gap-2">
          <button className="btn-primary" onClick={run} disabled={running || !question.trim()}>
            {running ? "Läuft…" : "Agent fragen"}
          </button>
          {running && (
            <button className="btn-secondary" onClick={() => abortRef.current?.abort()}>
              Abbrechen
            </button>
          )}
        </div>
        {error && <div className="text-red-600 text-[13px]">Fehler: {error}</div>}
        {events.length > 0 && (
          <div className="text-[12px] text-ink-muted font-mono space-y-0.5">
            {events.map((e, i) => (
              <div key={i}>[{e.scope}] {e.name}</div>
            ))}
          </div>
        )}
        {report && (
          <pre className="whitespace-pre-wrap text-[13px] bg-white border border-line rounded p-4">{report}</pre>
        )}
      </div>
    </div>
  );
}
