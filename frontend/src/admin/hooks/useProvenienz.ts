import { useCallback, useReducer, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * React Query hooks for the Provenienz tab.
 *
 * Endpoints:
 *   POST   /api/admin/provenienz/sessions
 *   GET    /api/admin/provenienz/sessions[?slug=...]
 *   GET    /api/admin/provenienz/sessions/{session_id}
 *   DELETE /api/admin/provenienz/sessions/{session_id}
 */

// ---- Types ----

export interface SessionMeta {
  session_id: string;
  slug: string;
  root_chunk_id: string;
  status: "open" | "closed";
  created_at: string;
  last_touched_at: string;
  pinned_approach_ids: string[];
  goal: string;
}

export interface ProvNode {
  node_id: string;
  session_id: string;
  kind: string;
  payload: Record<string, unknown>;
  actor: string;
  created_at: string;
}

export interface ProvEdge {
  edge_id: string;
  session_id: string;
  from_node: string;
  to_node: string;
  kind: string;
  reason: string | null;
  actor: string;
  created_at: string;
}

export interface SessionDetail {
  meta: SessionMeta;
  nodes: ProvNode[];
  edges: ProvEdge[];
}

export interface CreateSessionRequest {
  slug: string;
  root_chunk_id: string;
}

// ---- Step / decide types ----

export interface ActionProposalAlternative {
  label: string;
  args: Record<string, unknown>;
}

export interface GuidanceConsulted {
  kind: "reason" | "approach";
  id: string;
  summary: string;
  /** Approaches: false = manually pinned, true = auto-selected by
   *  matching selection_criteria. Reasons are always implicit-corpus
   *  (false). */
  auto_selected?: boolean;
  /** When auto_selected, the human-readable triggers that matched
   *  ("Anker-Typ 'chunk' in [chunk, claim]", "Ziel enthält: Beleg"). */
  selection_reasons?: string[];
}

export interface ActionProposal {
  node_id: string;
  session_id: string;
  kind: "action_proposal";
  payload: {
    step_kind: string;
    anchor_node_id: string;
    recommended: ActionProposalAlternative;
    alternatives: ActionProposalAlternative[];
    reasoning: string;
    guidance_consulted: GuidanceConsulted[];
  };
  actor: string;
  created_at: string;
}

export interface DecideResponse {
  decision_node: ProvNode;
  spawned_nodes: ProvNode[];
  spawned_edges: ProvEdge[];
}

export interface DecideRequest {
  proposal_node_id: string;
  accepted: "recommended" | "alt" | "override";
  alt_index?: number;
  reason?: string;
  override?: string;
}

// ---- fetchOk (shared util — duplicated from useComparison rather than refactored) ----

async function fetchOk(url: string, init: RequestInit, token: string): Promise<Response> {
  const r = await fetch(url, {
    ...init,
    headers: { ...(init.headers ?? {}), "X-Auth-Token": token },
  });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep status fallback */
    }
    throw new Error(detail);
  }
  return r;
}

// ---- Hooks ----

export interface DocElement {
  box_id: string;
  html_snippet: string;
  page: number; // parsed from "p<page>-..."
  text_preview: string; // HTML stripped, trimmed
}

export function useDocElements(slug: string, token: string) {
  return useQuery<DocElement[]>({
    queryKey: ["provenienz", "doc-elements", slug],
    enabled: !!slug && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/mineru`,
        { method: "GET" },
        token,
      );
      const body = (await r.json()) as {
        elements?: { box_id: string; html_snippet?: string }[];
      };
      const els = body.elements ?? [];
      return els.map((e) => {
        const m = /^p(\d+)-/.exec(e.box_id);
        const page = m ? Number(m[1]) : 0;
        const stripped = (e.html_snippet ?? "")
          .replace(/<[^>]*>/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        return {
          box_id: e.box_id,
          html_snippet: e.html_snippet ?? "",
          page,
          text_preview: stripped,
        };
      });
    },
  });
}

export function useSessions(slug: string, token: string) {
  return useQuery<SessionMeta[]>({
    queryKey: ["provenienz", "sessions", slug],
    enabled: !!slug && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions?slug=${encodeURIComponent(slug)}`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as SessionMeta[];
    },
  });
}

export function useSession(sessionId: string | null, token: string) {
  return useQuery<SessionDetail>({
    queryKey: ["provenienz", "session", sessionId],
    enabled: !!sessionId && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as SessionDetail;
    },
  });
}

export function useCreateSession(token: string) {
  const qc = useQueryClient();
  return useMutation<SessionMeta, Error, CreateSessionRequest>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      return (await r.json()) as SessionMeta;
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["provenienz", "sessions", created.slug] });
    },
  });
}

export interface PlanProposal {
  node_id: string;
  session_id: string;
  kind: "plan_proposal";
  payload: {
    next_step: string;
    target_anchor_id: string;
    tool: string | null;
    approach_id: string | null;
    reasoning: string;
    expected_outcome: string;
    confidence: number;
    fallback_plan: string;
    guidance_consulted?: GuidanceConsulted[];
  };
  actor: string;
  created_at: string;
}

export function useGetPlan(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<PlanProposal, Error, void>({
    mutationFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/plan`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
        token,
      );
      return (await r.json()) as PlanProposal;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useDeleteSession(token: string, slug: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (sessionId) => {
      await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}`,
        { method: "DELETE" },
        token,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "sessions", slug] });
    },
  });
}

export function useSetClaimGoal(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ProvNode, Error, { claimId: string; goal: string }>({
    mutationFn: async ({ claimId, goal }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/claims/${claimId}/goal`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal }),
        },
        token,
      );
      return (await r.json()) as ProvNode;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useSetGoal(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<SessionMeta, Error, string>({
    mutationFn: async (goal) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/goal`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal }),
        },
        token,
      );
      const out = (await r.json()) as { meta: SessionMeta };
      return out.meta;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
      qc.invalidateQueries({ queryKey: ["provenienz", "sessions"] });
    },
  });
}

export function useDeleteNode(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (nodeId) => {
      await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/nodes/${nodeId}`,
        { method: "DELETE" },
        token,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

// ---- Approach library ----

/** Auto-pin rules. Empty / missing fields = manual-pin only. AND-logic
 *  across present keys; OR-logic within each list. */
export interface ApproachSelectionCriteria {
  anchor_kinds?: string[];
  goal_contains?: string[];
  text_contains?: string[];
}

export type ApproachMode = "passive" | "active";

/** Reactive-Capability triggers (RC layer). Empty dict = non-reactive
 *  approach. AND across keys, OR within each list. */
export interface ApproachTriggers {
  verdicts?: string[];
  sentence_regex?: string[];
  claim_regex?: string[];
  topic_keywords?: string[];
}

export interface Approach {
  approach_id: string;
  name: string;
  version: number;
  step_kinds: string[];
  extra_system: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  selection_criteria: ApproachSelectionCriteria;
  /** "passive" = text-overlay im Meta-Planer-Prompt (Default).
   *  "active" = eigener LLM-Reasoning-Call als Sub-Agent + Beitrag
   *  zum Coordinator. Greift heute nur im next_step-Pfad. */
  mode: ApproachMode;
  /** Reactive-Capability triggers. Empty = non-reactive. */
  triggers: ApproachTriggers;
  /** "" = top-level. Non-empty = sub-skill of named parent. */
  parent_capability: string;
  /** Block injected into re_evaluate's extra_system when this
   *  capability fires + user accepts. */
  domain_rules: string;
}

export function useApproaches(token: string, opts?: { stepKind?: string; enabledOnly?: boolean }) {
  const stepKind = opts?.stepKind;
  const enabledOnly = opts?.enabledOnly ?? false;
  return useQuery<Approach[]>({
    queryKey: ["provenienz", "approaches", stepKind ?? "all", enabledOnly],
    enabled: !!token,
    queryFn: async () => {
      const params = new URLSearchParams();
      if (stepKind) params.set("step_kind", stepKind);
      params.set("enabled_only", String(enabledOnly));
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/approaches?${params}`,
        { method: "GET" },
        token,
      );
      const body = (await r.json()) as { approaches: Approach[] };
      return body.approaches;
    },
  });
}

export interface CreateApproachRequest {
  name: string;
  step_kinds: string[];
  extra_system: string;
  selection_criteria?: ApproachSelectionCriteria;
  mode?: ApproachMode;
  triggers?: ApproachTriggers;
  parent_capability?: string;
  domain_rules?: string;
}

export function useCreateApproach(token: string) {
  const qc = useQueryClient();
  return useMutation<Approach, Error, CreateApproachRequest>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/approaches`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      const out = (await r.json()) as { approach: Approach };
      return out.approach;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "approaches"] });
    },
  });
}

export interface PatchApproachRequest {
  enabled?: boolean;
  extra_system?: string;
  step_kinds?: string[];
  selection_criteria?: ApproachSelectionCriteria;
  mode?: ApproachMode;
  triggers?: ApproachTriggers;
  parent_capability?: string;
  domain_rules?: string;
}

export function usePatchApproach(token: string) {
  const qc = useQueryClient();
  return useMutation<Approach, Error, { approachId: string; patch: PatchApproachRequest }>({
    mutationFn: async ({ approachId, patch }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/approaches/${approachId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        },
        token,
      );
      const out = (await r.json()) as { approach: Approach };
      return out.approach;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "approaches"] });
    },
  });
}

export function useDeleteApproach(token: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (approachId) => {
      await fetchOk(
        `${apiBase()}/api/admin/provenienz/approaches/${approachId}`,
        { method: "DELETE" },
        token,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "approaches"] });
    },
  });
}

// ---- Agent introspection ----

export interface AgentLlmInfo {
  backend: string;
  model: string;
  base_url: string;
}

export interface AgentStepInfo {
  kind: string;
  label: string;
  input_kind: string;
  output_kind: string;
  uses_llm: boolean;
  uses_tool: string | null;
  rules: string[];
  system_prompt: string;
  user_template: string;
  expected_output: string;
}

export interface AgentToolInfo {
  name: string;
  label: string;
  description: string;
  when_to_use: string;
  scope: string;
  cost_hint: string;
  enabled: boolean;
  used_by: string[];
  /** Concrete trigger heuristic injected into the planner's prompt —
   *  tells the agent exactly when to capability_request this tool by
   *  its right name. Empty string = no specific guidance. */
  agent_hint: string;
}

export interface CapabilityRequestExample {
  session_id: string;
  slug: string;
  node_id: string;
  description: string;
  reasoning: string;
  created_at: string;
}

export interface CapabilityRequestAggregation {
  name: string;
  count: number;
  examples: CapabilityRequestExample[];
}

export function useCapabilityRequests(token: string) {
  return useQuery<CapabilityRequestAggregation[]>({
    queryKey: ["provenienz", "capability-requests"],
    enabled: !!token,
    staleTime: 30_000,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/capability-requests`,
        { method: "GET" },
        token,
      );
      const body = (await r.json()) as { requests: CapabilityRequestAggregation[] };
      return body.requests;
    },
  });
}

export function useTools(token: string) {
  return useQuery<AgentToolInfo[]>({
    queryKey: ["provenienz", "tools"],
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/tools`,
        { method: "GET" },
        token,
      );
      const body = (await r.json()) as { tools: AgentToolInfo[] };
      return body.tools;
    },
  });
}

export interface AgentRuleInfo {
  summary: string;
  trigger: string;
  storage: string;
  injection: string;
  applies_to: string[];
}

export interface AgentNextStepInfo {
  kind: "next_step";
  label: string;
  input_kind: string;
  output_kind: string;
  uses_llm: boolean;
  uses_tool: string | null;
  rules: string[];
  system_prompt: string;
  expected_output: string;
}

export interface AgentInfo {
  llm: AgentLlmInfo;
  next_step: AgentNextStepInfo;
  valid_steps_per_anchor: Record<string, string[]>;
  steps: AgentStepInfo[];
  tools: AgentToolInfo[];
  rules: Record<string, AgentRuleInfo>;
}

export function useAgentInfo(token: string) {
  return useQuery<AgentInfo>({
    queryKey: ["provenienz", "agent-info"],
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // info is static between deploys
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/agent-info`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as AgentInfo;
    },
  });
}

export interface NextStepResult {
  node_id: string;
  session_id: string;
  /** out_kind: "plan_proposal" (executable_step), "capability_request",
   *  or "manual_review". */
  kind: string;
  payload: {
    kind: "executable_step" | "capability_request" | "manual_review";
    name: string;
    description: string;
    reasoning: string;
    /** Phase-1.5 required field: how this step serves the session goal.
     *  Empty string when the LLM omitted it (UI shows a warning). */
    goal_alignment: string;
    considered_alternatives: { name: string; kind: string; why_not: string }[];
    confidence: number;
    tool: string | null;
    approach_id: string | null;
    anchor_node_id: string;
  };
  actor: string;
  created_at: string;
}

export function useNextStep(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<NextStepResult, Error, string>({
    mutationFn: async (anchorNodeId) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/next-step`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ anchor_node_id: anchorNodeId }),
        },
        token,
      );
      return (await r.json()) as NextStepResult;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

// ---- Live-Run streaming ----
//
// /next-step/stream emits SSE events as the planner walks its phases:
//   event: phase    → started / completed / failed for one phase
//   event: complete → final persisted Node
//   event: error    → unexpected backend exception
//
// useNextStepStream consumes that stream into an evolving phase-list +
// final result. The LiveRunPanel renders each phase as a card.

export type LiveRunPhaseStatus = "running" | "completed" | "failed";

/** One phase of a live run (gather_guidance, gather_tools, llm_call,
 *  validate, persist). Started + completed events of the same phase
 *  collapse into one record so the UI renders a single card per phase. */
export interface LiveRunPhase {
  phase: string;
  label: string;
  status: LiveRunPhaseStatus;
  startedAtMs: number;
  completedAtMs: number | null;
  durationMs: number | null;
  /** Merged payload: started-event fields are kept, completed-event
   *  fields overlay them (since "completed" carries the actual result). */
  payload: Record<string, unknown>;
  error: string | null;
}

interface BackendPhaseEvent {
  type: "phase";
  phase: string;
  status: "started" | "completed" | "failed";
  label: string;
  ms_since_run_start: number;
  ms_elapsed: number;
  payload: Record<string, unknown>;
  error: string | null;
}

interface BackendCompleteEvent {
  type: "complete";
  node: NextStepResult;
}

interface RunState {
  phases: LiveRunPhase[];
  result: NextStepResult | null;
  error: string | null;
  isRunning: boolean;
  /** Wall-clock start (Date.now()), null when idle. */
  startedAt: number | null;
}

const INITIAL_RUN: RunState = {
  phases: [],
  result: null,
  error: null,
  isRunning: false,
  startedAt: null,
};

type RunAction =
  | { type: "start" }
  | { type: "phase"; ev: BackendPhaseEvent }
  | { type: "complete"; node: NextStepResult }
  | { type: "error"; message: string }
  | { type: "reset" };

function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "start":
      return { ...INITIAL_RUN, isRunning: true, startedAt: Date.now() };
    case "phase": {
      const { ev } = action;
      const phases = [...state.phases];
      const idx = phases.findIndex((p) => p.phase === ev.phase);
      if (ev.status === "started") {
        const next: LiveRunPhase = {
          phase: ev.phase,
          label: ev.label,
          status: "running",
          startedAtMs: ev.ms_since_run_start,
          completedAtMs: null,
          durationMs: null,
          payload: ev.payload,
          error: null,
        };
        if (idx === -1) phases.push(next);
        else phases[idx] = next;
      } else {
        // completed / failed — merge onto the existing record.
        const existing = idx === -1 ? null : phases[idx];
        const merged: LiveRunPhase = {
          phase: ev.phase,
          label: ev.label,
          status: ev.status === "failed" ? "failed" : "completed",
          startedAtMs: existing?.startedAtMs ?? ev.ms_since_run_start - ev.ms_elapsed,
          completedAtMs: ev.ms_since_run_start,
          durationMs: ev.ms_elapsed,
          payload: { ...(existing?.payload ?? {}), ...ev.payload },
          error: ev.error,
        };
        if (idx === -1) phases.push(merged);
        else phases[idx] = merged;
      }
      return { ...state, phases };
    }
    case "complete":
      return { ...state, result: action.node, isRunning: false };
    case "error":
      return { ...state, error: action.message, isRunning: false };
    case "reset":
      return INITIAL_RUN;
  }
}

/** Parse one ``event: X\ndata: Y`` SSE block. Returns null on malformed
 *  input — caller skips and keeps reading. */
function parseSseBlock(
  block: string,
): BackendPhaseEvent | BackendCompleteEvent | { type: "error"; message: string } | null {
  const lines = block.split("\n");
  let event = "message";
  const dataLines: string[] = [];
  for (const ln of lines) {
    if (ln.startsWith("event:")) event = ln.slice(6).trim();
    else if (ln.startsWith("data:")) dataLines.push(ln.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    if (event === "phase") return data as unknown as BackendPhaseEvent;
    if (event === "complete") return data as unknown as BackendCompleteEvent;
    if (event === "error") return data as unknown as { type: "error"; message: string };
  } catch {
    return null;
  }
  return null;
}

/** Optional second arg for ``stream.start``. ``triggeredFromNodeId``
 *  carries the click-trail when "Was als nächstes?" is invoked from a
 *  Folge-Knoten that re-anchors to its parent (e.g. a Bewertungs-Tile
 *  routes to the parent search_result). The backend persists it on
 *  the spawned plan_proposal so the canvas can draw a "triggered-from"
 *  edge back to the trail node. */
export interface NextStepStartOptions {
  triggered_from_node_id?: string;
}

export interface UseNextStepStream extends RunState {
  start: (
    anchorNodeId: string,
    options?: NextStepStartOptions,
  ) => Promise<void>;
  reset: () => void;
}

export function useNextStepStream(
  token: string,
  sessionId: string,
): UseNextStepStream {
  const [state, dispatch] = useReducer(runReducer, INITIAL_RUN);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  const start = useCallback(
    async (
      anchorNodeId: string,
      options: NextStepStartOptions = {},
    ): Promise<void> => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: "start" });

      // Click-trail forwarded only when set — backend treats absent
      // and empty as the same "no trail" case, but the explicit
      // omission keeps the request body shape identical to today's
      // direct-anchor invocations so the diff is contained.
      const requestBody: {
        anchor_node_id: string;
        triggered_from_node_id?: string;
      } = { anchor_node_id: anchorNodeId };
      if (options.triggered_from_node_id) {
        requestBody.triggered_from_node_id = options.triggered_from_node_id;
      }

      try {
        const r = await fetch(
          `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/next-step/stream`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Auth-Token": token,
              Accept: "text/event-stream",
            },
            body: JSON.stringify(requestBody),
            signal: ctrl.signal,
          },
        );
        if (!r.ok) {
          let detail = `${r.status} ${r.statusText}`;
          try {
            const body = (await r.json()) as { detail?: string };
            if (body && typeof body.detail === "string") detail = body.detail;
          } catch {
            /* keep status fallback */
          }
          dispatch({ type: "error", message: detail });
          return;
        }
        if (!r.body) {
          dispatch({ type: "error", message: "Keine Stream-Antwort vom Server" });
          return;
        }

        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx = buf.indexOf("\n\n");
          while (idx !== -1) {
            const block = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const parsed = parseSseBlock(block);
            if (parsed) {
              if (parsed.type === "phase") dispatch({ type: "phase", ev: parsed });
              else if (parsed.type === "complete")
                dispatch({ type: "complete", node: parsed.node });
              else dispatch({ type: "error", message: parsed.message });
            }
            idx = buf.indexOf("\n\n");
          }
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        dispatch({
          type: "error",
          message: e instanceof Error ? e.message : "Stream fehlgeschlagen",
        });
      } finally {
        // Always refetch the session — the run wrote a Node either way
        // (final on success, audit-only on early error after persist).
        qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
      }
    },
    [token, sessionId, qc],
  );

  return { ...state, start, reset };
}

export interface ReflectionResult {
  node_id: string;
  session_id: string;
  kind: "reflection";
  payload: {
    anchor_node_id: string;
    step_kind_reviewed: string;
    self_assessment: "vollständig" | "lückenhaft" | "fehlerhaft";
    missed_statements: string[];
    concerns: string[];
    recommendation: "accept" | "re-evaluate" | "expand-context";
    recommended_focus: string;
    audit?: Record<string, unknown>;
  };
  actor: string;
  created_at: string;
}

export function useReflect(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ReflectionResult, Error, string>({
    mutationFn: async (proposalNodeId) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/reflect`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ proposal_node_id: proposalNodeId }),
        },
        token,
      );
      return (await r.json()) as ReflectionResult;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export interface ReEvaluateResult {
  action_proposal: ActionProposal;
  gate_update: ProvNode;
}

export function useReEvaluate(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ReEvaluateResult,
    Error,
    { gateNodeId: string; capabilityIds: string[] }
  >({
    mutationFn: async ({ gateNodeId, capabilityIds }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/re-evaluate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            capability_gate_node_id: gateNodeId,
            capability_ids: capabilityIds,
          }),
        },
        token,
      );
      return (await r.json()) as ReEvaluateResult;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useDecomposeHit(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ActionProposal, Error, string>({
    mutationFn: async (searchResultNodeId) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/decompose-hit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ search_result_node_id: searchResultNodeId }),
        },
        token,
      );
      return (await r.json()) as ActionProposal;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function usePromoteSearchResult(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<ProvNode, Error, string>({
    mutationFn: async (searchResultNodeId) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/promote-search-result`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ search_result_node_id: searchResultNodeId }),
        },
        token,
      );
      return (await r.json()) as ProvNode;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

// ---- Step routes ----

function stepRoutePost<TBody>(
  token: string,
  sessionId: string,
  path: string,
): (body: TBody) => Promise<ActionProposal> {
  return async (body: TBody) => {
    const r = await fetchOk(
      `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/${path}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      token,
    );
    return (await r.json()) as ActionProposal;
  };
}

export function useExtractClaims(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ActionProposal,
    Error,
    { chunk_node_id: string; provider?: string }
  >({
    mutationFn: stepRoutePost(token, sessionId, "extract-claims"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useFormulateTask(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ActionProposal,
    Error,
    { claim_node_id: string; provider?: string }
  >({
    mutationFn: stepRoutePost(token, sessionId, "formulate-task"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useSearchStep(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ActionProposal,
    Error,
    { task_node_id: string; top_k?: number }
  >({
    mutationFn: stepRoutePost(token, sessionId, "search"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useEvaluate(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ActionProposal,
    Error,
    {
      search_result_node_id: string;
      /** Optional — backend resolves from the search_result chain
       *  (search_result → task.focus_claim_id) when omitted. Lets the
       *  agent's plan_proposal flow accept evaluate without the panel
       *  having to know the upstream claim. */
      against_claim_id?: string;
      provider?: string;
    }
  >({
    mutationFn: stepRoutePost(token, sessionId, "evaluate"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useProposeStop(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<
    ActionProposal,
    Error,
    { anchor_node_id: string; provider?: string }
  >({
    mutationFn: stepRoutePost(token, sessionId, "propose-stop"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}

export function useDecide(token: string, sessionId: string) {
  const qc = useQueryClient();
  return useMutation<DecideResponse, Error, DecideRequest>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/sessions/${sessionId}/decide`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      return (await r.json()) as DecideResponse;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "session", sessionId] });
    },
  });
}
