import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * Hooks for the local vLLM subprocess control panel in the Synthesise
 * sidebar. Backend: /api/admin/llm/{status,start,stop}.
 *
 * Polling cadence:
 *   - 5 s when state is "running" or "stopped" (cheap)
 *   - 2 s when state is "starting" or "error" (we want to see the
 *     transition fast)
 */

export type LlmState = "stopped" | "starting" | "running" | "error";

export interface LlmStatus {
  state: LlmState;
  pid: number | null;
  model: string | null;
  base_url: string | null;
  healthy: boolean;
  error: string | null;
  log_tail: string[];
  vllm_cli_available: boolean;
}

async function fetchStatus(token: string): Promise<LlmStatus> {
  const r = await fetch(`${apiBase()}/api/admin/llm/status`, {
    headers: { "X-Auth-Token": token },
  });
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json() as Promise<LlmStatus>;
}

export function useLlmStatus(token: string) {
  return useQuery<LlmStatus>({
    queryKey: ["llm-status"],
    queryFn: () => fetchStatus(token),
    refetchInterval: (query) => {
      const s = query.state.data?.state;
      return s === "starting" || s === "error" ? 2_000 : 5_000;
    },
    retry: false,
  });
}

export function useLlmStart(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const r = await fetch(`${apiBase()}/api/admin/llm/start`, {
        method: "POST",
        headers: { "X-Auth-Token": token },
      });
      if (!r.ok) throw new Error(`start failed: ${r.status}`);
      return r.json() as Promise<LlmStatus>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-status"] }),
  });
}

export function useLlmStop(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const r = await fetch(`${apiBase()}/api/admin/llm/stop`, {
        method: "POST",
        headers: { "X-Auth-Token": token },
      });
      if (!r.ok) throw new Error(`stop failed: ${r.status}`);
      return r.json() as Promise<LlmStatus>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-status"] }),
  });
}

// ── Model picker (Phase: top-bar control) ──────────────────────────────

export interface ModelOption {
  name: string;
  label: string;
  parameters_b: number;
  vram_bf16_gb: number;
  fits_24gb_bf16: boolean;
  multilingual: boolean;
  license: string;
  notes: string;
}

export interface ModelsResponse {
  models: ModelOption[];
  current: string | null;
}

export function useLlmModels(token: string) {
  return useQuery<ModelsResponse>({
    queryKey: ["llm-models"],
    queryFn: async () => {
      const r = await fetch(`${apiBase()}/api/admin/llm/models`, {
        headers: { "X-Auth-Token": token },
      });
      if (!r.ok) throw new Error(`models ${r.status}`);
      return r.json() as Promise<ModelsResponse>;
    },
    // Curated list rarely changes; current model only on /select-model
    // which we invalidate manually below.
    staleTime: 60_000,
  });
}

export function useLlmSelectModel(token: string) {
  const qc = useQueryClient();
  return useMutation<LlmStatus, Error, string>({
    mutationFn: async (modelName) => {
      const r = await fetch(`${apiBase()}/api/admin/llm/select-model`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Token": token,
        },
        body: JSON.stringify({ model_name: modelName }),
      });
      if (!r.ok) {
        let detail = `${r.status} ${r.statusText}`;
        try {
          const body = (await r.json()) as { detail?: string };
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch {
          /* keep status fallback */
        }
        throw new Error(detail);
      }
      return r.json() as Promise<LlmStatus>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-status"] });
      qc.invalidateQueries({ queryKey: ["llm-models"] });
    },
  });
}
