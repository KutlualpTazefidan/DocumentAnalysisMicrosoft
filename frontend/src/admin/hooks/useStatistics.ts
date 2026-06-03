// frontend/src/admin/hooks/useStatistics.ts
import { useQuery } from "@tanstack/react-query";
import { apiBase } from "../api/adminClient";

/** Field names mirror the Pydantic models in
 *  features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py
 *  1:1. Do not rename without updating both ends. */

export interface DiagnosticCounts {
  split: number;
  no_decomposition: number;
  clean: number;
  total: number;
}

export interface ExtractStats {
  slug: string;
  diagnostics: DiagnosticCounts;
  register_boxes: number;
  total_boxes: number;
  register_rate: number | null;
}

export interface VoteDistributionRow {
  entry_id: string;
  text_short: string;
  approved: number;
  rejected: number;
}

export interface SyntheseStats {
  slug: string;
  questions_created: number;
  questions_deprecated: number;
  survival_rate: number | null;
  vote_approved: number;
  vote_rejected: number;
  vote_approval_rate: number | null;
  vote_distribution: VoteDistributionRow[];
}

export interface ProvenienzStats {
  slug: string;
  plan_proposals: number;
  expert_overrides: number;
  correction_rate: number | null;
}

export interface CapabilityWish {
  name: string;
  count: number;
  by_actor: Record<string, number>;
  skill_bucket: string;
}

export interface CapabilityWishes {
  wishes: CapabilityWish[];
}

async function fetchOk(url: string, token: string): Promise<Response> {
  const r = await fetch(url, { headers: { "X-Auth-Token": token } });
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

export function useExtractStats(slug: string, token: string) {
  return useQuery<ExtractStats>({
    queryKey: ["stats", "extract", slug],
    queryFn: async () => {
      const r = await fetchOk(`${apiBase()}/api/admin/statistics/extract/${encodeURIComponent(slug)}`, token);
      return r.json();
    },
    retry: false,
  });
}

export function useSyntheseStats(slug: string, token: string) {
  return useQuery<SyntheseStats>({
    queryKey: ["stats", "synthese", slug],
    queryFn: async () => {
      const r = await fetchOk(`${apiBase()}/api/admin/statistics/synthese/${encodeURIComponent(slug)}`, token);
      return r.json();
    },
    retry: false,
  });
}

export function useProvenienzStats(slug: string, token: string) {
  return useQuery<ProvenienzStats>({
    queryKey: ["stats", "provenienz", slug],
    queryFn: async () => {
      const r = await fetchOk(`${apiBase()}/api/admin/statistics/provenienz/${encodeURIComponent(slug)}`, token);
      return r.json();
    },
    retry: false,
  });
}

export function useCapabilityWishes(token: string) {
  return useQuery<CapabilityWishes>({
    queryKey: ["stats", "capability-wishes"],
    queryFn: async () => {
      const r = await fetchOk(`${apiBase()}/api/admin/statistics/capability-wishes`, token);
      return r.json();
    },
    retry: false,
  });
}
