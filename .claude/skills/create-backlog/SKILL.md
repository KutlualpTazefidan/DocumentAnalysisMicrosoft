---
name: create-backlog
description: Use when the user wants to create backlog items, plan tasks, write user stories, or convert rough ideas into structured backlog entries. Trigger whenever the user describes features they want to build, mentions tasks they want to plan, or asks to organize their work — even if they don't say "backlog" explicitly.
---

# Create Backlog

Turn raw thoughts into structured backlog items and save them to `backlog.md`.

## What you receive

The user will write freely — in German, English, or mixed — describing one or more things they want to build. They may include rough task descriptions in everyday language. Your job is to transform this into clean, professional backlog items in English.

## Step 1: Understand how many items there are

Read the input and decide how many distinct features or topics are described. Each distinct feature becomes its own backlog item. Don't merge unrelated things together.

## Step 2: For each item, build the user story

**Format:**
> As a developer, I want to [goal] so that [value].

- The role is always **developer** — never ask about this
- The goal comes from what the user described
- The "so that" part is the value or outcome — infer it from context. If you genuinely can't figure out the purpose, ask one short clarifying question before proceeding

## Step 3: Reformulate the tasks

The user gives rough tasks in informal language. Your job:
- Rewrite them clearly in English
- Break down any task that would take more than **2-3 days** into smaller subtasks
- If a task is vague (e.g. "alles aufsetzen"), split it into concrete steps

## Step 4: Generate acceptance criteria

Write 3-5 acceptance criteria that define "done" for this item. Base them on the tasks — each task should be reflected in at least one criterion.

## Step 5: Decide priority

Pick one: **Urgent / Important / Medium / Low**

Use this heuristic:
- Blocks other work → Urgent
- Core feature needed soon → Important  
- Useful but not blocking → Medium
- Nice to have → Low

Don't ask the user — decide yourself. They can adjust later.

## Step 6: Append to backlog.md

Always write to `backlog.md` in the current working directory. Append — don't overwrite. No confirmation needed.

Use this exact format for each item:

```markdown
---

## [YYYY-MM-DD] — [Feature Title]

**Priority:** [Urgent | Important | Medium | Low]

### User Story
As a developer, I want to [goal] so that [value].

### Tasks
- [ ] [Task 1]
- [ ] [Task 2]
- [ ] [Task 3]

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]
```

If multiple items were created in one run, separate them with `---` but share a single date header per session.

## When to ask clarifying questions

Ask **only** if:
- The "so that" value is genuinely unclear and you can't infer it
- A specific task is so vague you can't break it down meaningfully

Keep questions short — one per blocker. Don't ask about role, priority, or bucket.

## Example

**User input:**
> qdrant einrichten für rag pipeline — docker aufsetzen, schema definieren, testen ob insert und query klappt

**Output appended to backlog.md:**

```markdown
---

## 2026-04-16 — Set Up Qdrant as Local Vector Store

**Priority:** Important

### User Story
As a developer, I want to set up Qdrant as the local vector store for the RAG pipeline so that embeddings can be stored and queried reliably.

### Tasks
- [ ] Install and run Qdrant locally via Docker
- [ ] Define collection schema and configure embedding dimensions
- [ ] Test insert and query operations end-to-end

### Acceptance Criteria
- [ ] Qdrant runs stable locally via Docker
- [ ] Collection schema and embedding dimensions are configured correctly
- [ ] Insert and query operations return expected results
```
