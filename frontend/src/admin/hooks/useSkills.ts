import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/**
 * React Query hooks for the unified Skill library.
 *
 * Endpoints (Task 9):
 *   GET    /api/admin/provenienz/skills
 *   POST   /api/admin/provenienz/skills            (201)
 *   GET    /api/admin/provenienz/skills/{id}
 *   PATCH  /api/admin/provenienz/skills/{id}
 *   DELETE /api/admin/provenienz/skills/{id}       (204)
 *
 * The backend returns a Skill object directly (no envelope), unlike
 * the legacy /approaches routes which wrap in `{approach: ...}`.
 */

// ---- Types (mirror local_pdf.provenienz.skills) ----

export type SkillKind =
  | "prompt-overlay"
  | "subagent"
  | "enrichment"
  | "reactive"
  | "note";

export interface TriggerConditions {
  verdicts: string[];
  sentence_regex: string[];
  claim_regex: string[];
  topic_keywords: string[];
  anchor_kinds: string[];
  goal_contains: string[];
  text_contains: string[];
}

export interface SkillPrompt {
  free_text: string;
  questions: string[];
  domain_rules: string;
}

export interface SkillOutput {
  /** e.g. "claim_background" */
  annotation_kind: string;
  /** e.g. "claim" — required for enrichment skills. */
  attaches_to: string;
  consumed_by: string[];
}

export interface Skill {
  skill_id: string;
  name: string;
  version: number;
  enabled: boolean;
  description: string;
  created_at: string;
  updated_at: string;

  skill_kind: SkillKind;
  fires_on: string[];
  conditions: TriggerConditions;
  parent_skill: string;
  prompt: SkillPrompt;
  output: SkillOutput;
}

/** Body for POST /skills — server stamps id/version/timestamps. */
export type CreateSkillRequest = Omit<
  Skill,
  "skill_id" | "version" | "created_at" | "updated_at"
>;

/** Body for PATCH /skills/{id} — every field optional, server merges. */
export type PatchSkillRequest = Partial<
  Omit<Skill, "skill_id" | "version" | "created_at" | "updated_at" | "name">
>;

// ---- fetchOk (shared util — duplicated from useProvenienz rather than refactored) ----

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

export function useSkills(token: string) {
  return useQuery<Skill[]>({
    queryKey: ["provenienz", "skills"],
    enabled: !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as Skill[];
    },
  });
}

export function useSkill(token: string, skillId: string | null) {
  return useQuery<Skill>({
    queryKey: ["provenienz", "skills", skillId],
    enabled: !!token && !!skillId,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills/${skillId}`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as Skill;
    },
  });
}

export function useCreateSkill(token: string) {
  const qc = useQueryClient();
  return useMutation<Skill, Error, CreateSkillRequest>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      return (await r.json()) as Skill;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provenienz", "skills"] });
    },
  });
}

export function useUpdateSkill(token: string) {
  const qc = useQueryClient();
  return useMutation<
    Skill,
    Error,
    { skill_id: string; patch: PatchSkillRequest }
  >({
    mutationFn: async ({ skill_id, patch }) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills/${skill_id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        },
        token,
      );
      return (await r.json()) as Skill;
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["provenienz", "skills"] });
      qc.invalidateQueries({
        queryKey: ["provenienz", "skills", variables.skill_id],
      });
    },
  });
}

/** One row from `{data_root}/skills/skill_runs.jsonl`. Newest first. */
export interface SkillRun {
  skill_id: string;
  skill_name: string;
  skill_version: number;
  n_inputs: number;
  n_outputs: number;
  success: boolean;
  ts: string;
}

export function useSkillRuns(skillId: string | null, token: string) {
  return useQuery<SkillRun[]>({
    queryKey: ["provenienz", "skills", skillId, "runs"],
    enabled: !!skillId && !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills/${skillId}/runs`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as SkillRun[];
    },
  });
}

export function useDeleteSkill(token: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (skillId) => {
      await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills/${skillId}`,
        { method: "DELETE" },
        token,
      );
    },
    onSuccess: (_data, skillId) => {
      qc.invalidateQueries({ queryKey: ["provenienz", "skills"] });
      qc.invalidateQueries({ queryKey: ["provenienz", "skills", skillId] });
    },
  });
}
