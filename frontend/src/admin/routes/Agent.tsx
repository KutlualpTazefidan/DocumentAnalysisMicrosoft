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
      </div>
    </div>
  );
}
