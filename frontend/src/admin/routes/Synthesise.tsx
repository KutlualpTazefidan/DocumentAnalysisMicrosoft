import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { DocStepTabs } from "../components/DocStepTabs";
import { T } from "../styles/typography";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8001";

interface SynthesiseTestResponse {
  response: string;
  model: string;
  elapsed_seconds: number;
}

interface SynthesiseInnerProps {
  slug: string;
  token: string;
}

function SynthesiseInner({ slug, token }: SynthesiseInnerProps): JSX.Element {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SynthesiseTestResponse | null>(null);
  const { error: toastError } = useToast();

  async function handleTest() {
    if (!prompt.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/docs/${slug}/synthesise/test`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Token": token,
        },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      const data: SynthesiseTestResponse = await res.json();
      setResult(data);
    } catch (err) {
      toastError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-8 w-full max-w-lg space-y-4">
          <h2 className={`${T.cardTitle} text-slate-800`}>Test LLM</h2>

          <textarea
            aria-label="LLM prompt"
            className={`w-full border border-slate-300 rounded px-3 py-2 ${T.body} resize-y min-h-[96px] focus:outline-none focus:ring-2 focus:ring-blue-400`}
            placeholder="Summarize the first paragraph of this document"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
          />

          <button
            aria-label="Test LLM"
            className={`w-full bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed font-medium ${T.body}`}
            onClick={handleTest}
            disabled={loading || !prompt.trim()}
          >
            {loading ? "Asking…" : "Test LLM"}
          </button>

          {result && (
            <div aria-label="LLM response" className="space-y-1">
              <p className={T.bodyMuted}>
                {result.model} &middot; {result.elapsed_seconds.toFixed(2)}s
              </p>
              <pre className={`whitespace-pre-wrap ${T.body} text-slate-800 bg-slate-50 border border-slate-200 rounded p-3`}>
                {result.response}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function Synthesise() {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <SynthesiseInner slug={slug!} token={token} />;
}
