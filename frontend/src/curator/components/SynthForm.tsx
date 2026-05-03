import { useState, type FormEvent } from "react";
import type { SynthesiseRequest } from "../../shared/types/domain";

interface Props {
  defaultModel?: string;
  onSubmit: (req: SynthesiseRequest) => void;
  disabled?: boolean;
}

export function SynthForm({ defaultModel = "gpt-4o-mini", onSubmit, disabled }: Props) {
  const [llmModel, setLlmModel] = useState(defaultModel);
  const [dryRun, setDryRun] = useState(true);
  const [maxQuestions, setMaxQuestions] = useState(20);
  const [maxPromptTokens, setMaxPromptTokens] = useState(8000);
  const [promptTemplateVersion, setPromptTemplateVersion] = useState("v1");
  const [temperature, setTemperature] = useState(0.0);
  const [startFrom, setStartFrom] = useState("");
  const [limit, setLimit] = useState<string>("");
  const [resume, setResume] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      llm_model: llmModel,
      dry_run: dryRun,
      max_questions_per_element: maxQuestions,
      max_prompt_tokens: maxPromptTokens,
      prompt_template_version: promptTemplateVersion,
      temperature,
      start_from: startFrom.trim() || null,
      limit: limit.trim() ? Number(limit) : null,
      resume,
    });
  }

  return (
    <form className="space-y-4 max-w-md" onSubmit={handleSubmit}>
      <label className="block">
        <span className="text-sm font-medium text-slate-700">LLM Model</span>
        <input
          className="input mt-1"
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={dryRun}
          onChange={(e) => setDryRun(e.target.checked)}
        />
        <span className="text-sm">Dry-run (keine LLM-Calls, nur Token-Schätzung)</span>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max questions/element</span>
          <input
            type="number"
            className="input mt-1"
            value={maxQuestions}
            onChange={(e) => setMaxQuestions(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max prompt tokens</span>
          <input
            type="number"
            className="input mt-1"
            value={maxPromptTokens}
            onChange={(e) => setMaxPromptTokens(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Prompt template</span>
          <input
            className="input mt-1"
            value={promptTemplateVersion}
            onChange={(e) => setPromptTemplateVersion(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Temperature</span>
          <input
            type="number"
            step="0.1"
            className="input mt-1"
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Start from (element_id)</span>
          <input
            className="input mt-1"
            value={startFrom}
            onChange={(e) => setStartFrom(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Limit (#elements)</span>
          <input
            type="number"
            className="input mt-1"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
      </div>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={resume}
          onChange={(e) => setResume(e.target.checked)}
        />
        <span className="text-sm">Resume — überspringe schon-erfasste Elemente</span>
      </label>
      <button type="submit" className="btn-primary" disabled={disabled}>
        Synthesise starten
      </button>
    </form>
  );
}
