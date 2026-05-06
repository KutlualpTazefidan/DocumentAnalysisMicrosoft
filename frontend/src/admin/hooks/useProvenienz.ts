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

export interface Approach {
  approach_id: string;
  name: string;
  version: number;
  step_kinds: string[];
  extra_system: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
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

export interface AgentInfo {
  llm: AgentLlmInfo;
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
      against_claim_id: string;
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
