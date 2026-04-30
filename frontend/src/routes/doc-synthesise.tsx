import { useParams } from "react-router-dom";
import { TopBar } from "../components/TopBar";
import { SynthForm } from "../components/SynthForm";
import { SynthProgress } from "../components/SynthProgress";
import { SynthSummary } from "../components/SynthSummary";
import { useSynthesise } from "../hooks/useSynthesise";

export function DocSynthesise() {
  const { slug } = useParams<{ slug: string }>();
  const synth = useSynthesise();

  if (!slug) return <p>Missing slug.</p>;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1 p-8 max-w-3xl mx-auto w-full space-y-6">
        <h1 className="text-2xl font-semibold">Synthesise — {slug}</h1>
        {synth.status === "idle" || synth.status === "error" || synth.status === "cancelled" ? (
          <>
            {synth.status === "error" && synth.fatalError ? (
              <p role="alert" className="text-red-700">
                Fehler: {synth.fatalError}
              </p>
            ) : null}
            {synth.status === "cancelled" ? (
              <p className="text-slate-600">Abgebrochen.</p>
            ) : null}
            <SynthForm
              onSubmit={(req) => synth.start({ slug, request: req })}
              disabled={false}
            />
          </>
        ) : null}
        {(synth.status === "submitting" ||
          synth.status === "streaming" ||
          synth.status === "complete") && synth.lines.length > 0 ? (
          <SynthProgress lines={synth.lines} totals={synth.totals} />
        ) : null}
        {synth.status === "streaming" ? (
          <button onClick={synth.cancel} className="btn-secondary">
            Abbrechen
          </button>
        ) : null}
        {synth.status === "complete" ? (
          <SynthSummary slug={slug} totals={synth.totals} onReset={synth.reset} />
        ) : null}
      </main>
    </div>
  );
}
