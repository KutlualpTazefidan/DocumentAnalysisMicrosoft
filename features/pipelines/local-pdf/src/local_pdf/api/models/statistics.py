"""Pydantic response models for /api/admin/statistics/*.

Field names mirror the TypeScript shapes in
``frontend/src/admin/hooks/useStatistics.ts`` 1:1 (no camelCase
rename — matches the existing /questions endpoint style).
"""

from __future__ import annotations

from pydantic import BaseModel


class DiagnosticCounts(BaseModel):
    split: int
    no_decomposition: int
    clean: int
    total: int


class ExtractStats(BaseModel):
    slug: str
    diagnostics: DiagnosticCounts
    register_boxes: int
    total_boxes: int
    register_rate: float | None


class VoteDistributionRow(BaseModel):
    entry_id: str
    text_short: str
    approved: int
    rejected: int


class SyntheseStats(BaseModel):
    slug: str
    questions_created: int
    questions_deprecated: int
    survival_rate: float | None
    vote_approved: int
    vote_rejected: int
    vote_approval_rate: float | None
    vote_distribution: list[VoteDistributionRow]


class ProvenienzStats(BaseModel):
    slug: str
    plan_proposals: int
    expert_overrides: int
    correction_rate: float | None


class CapabilityWish(BaseModel):
    name: str
    count: int
    by_actor: dict[str, int]
    skill_bucket: str


class CapabilityWishes(BaseModel):
    wishes: list[CapabilityWish]
