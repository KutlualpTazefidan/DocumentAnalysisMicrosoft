"""Unified Skill model: kind-tagged guidance records for the provenienz audit graph.

The skill_kind enum collapses what used to be a zoo of overlapping concepts
(prompt overlays, sub-agent expertise, enrichment annotations, reactive
domain rules, and free-form curator notes) into a single record schema.
Each kind constrains which fields are required:

  - PROMPT_OVERLAY  : non-empty fires_on; prompt text injected into a
                      step's system prompt.
  - SUBAGENT        : non-empty fires_on; runs as a separate LLM call.
  - ENRICHMENT      : non-empty fires_on; output.attaches_to declares
                      the anchor kind the annotation pins to.
  - REACTIVE        : non-empty fires_on; conditions match an evaluation's
                      verdict / sentence text / claim text.
  - NOTE            : free-form curator note; fires_on may be empty
                      (the only globally-stored kind).

Storage operations live in ``local_pdf.provenienz.skills_storage`` (Task 2).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class SkillKind(StrEnum):
    PROMPT_OVERLAY = "prompt-overlay"
    SUBAGENT = "subagent"
    ENRICHMENT = "enrichment"
    REACTIVE = "reactive"
    NOTE = "note"


class TriggerConditions(BaseModel):
    """AND-across-keys, OR-within-each-list trigger predicates."""

    verdicts: list[str] = Field(default_factory=list)
    sentence_regex: list[str] = Field(default_factory=list)
    claim_regex: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    anchor_kinds: list[str] = Field(default_factory=list)
    goal_contains: list[str] = Field(default_factory=list)
    text_contains: list[str] = Field(default_factory=list)


class SkillPrompt(BaseModel):
    """Prompt fragments injected into the consuming step's LLM call."""

    free_text: str = ""
    questions: list[str] = Field(default_factory=list)
    domain_rules: str = ""


class SkillOutput(BaseModel):
    """Where the skill's product lands in the audit graph."""

    annotation_kind: str = ""
    attaches_to: str = ""
    consumed_by: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    skill_id: str
    name: str
    version: int
    enabled: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    skill_kind: SkillKind
    fires_on: list[str] = Field(default_factory=list)
    conditions: TriggerConditions = Field(default_factory=TriggerConditions)
    parent_skill: str = ""
    prompt: SkillPrompt = Field(default_factory=SkillPrompt)
    output: SkillOutput = Field(default_factory=SkillOutput)

    @model_validator(mode="after")
    def _validate_kind_specific(self) -> Skill:
        if self.skill_kind != SkillKind.NOTE and not self.fires_on:
            raise ValueError(f"fires_on must be non-empty for skill_kind={self.skill_kind}")
        if self.skill_kind == SkillKind.ENRICHMENT and not self.output.attaches_to:
            raise ValueError("enrichment skills must declare output.attaches_to")
        return self
