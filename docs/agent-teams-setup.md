# Agent Teams: parallel Claude Code sessions

Status: experimental. Last reviewed: 2026-04-29.

## Why

Some work packages are independent enough to run in parallel — for example, two
unrelated features on different branches, or a backend/frontend split. Three
options exist for parallelism in Claude Code; we use them at different scopes:

| Scope | Mechanism | Trade-off |
|---|---|---|
| Sub-tasks of one feature | Subagents (Agent tool) inside one session | Shared context budget, results return to lead |
| Multi-perspective review of one diff | Agent teams (lead + teammates) | Each has its own context; teammates can message each other |
| Two unrelated work packages | Two top-level `claude` sessions, each in its own git worktree | Full independence; merge cost when work overlaps |

Running two top-level `claude` sessions in the **same** working directory
corrupts file state (interleaved edits, conflicting checkpoints). Worktrees
solve that. Agent teams gives lead/teammate coordination on top, when needed.

## What

- **Git worktrees** — `man git-worktree`. Same `.git`, multiple working
  directories, each on its own branch.
- **Agent teams** — official Claude Code experimental feature. A lead session
  spawns teammates with their own context; teammates share a task list and can
  message each other directly. Docs:
  https://code.claude.com/docs/en/agent-teams.md

## Setup

### 1. Enable the experimental flag (personal, not team-wide)

In `.claude/settings.local.json` (gitignored):

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

Takes effect on the **next** `claude` start, not the current session. The flag
stays in `settings.local.json` rather than `settings.json` because it's
experimental and per-machine — committing it would silently enable an
experimental feature for every teammate cloning the repo.

### 2. Create one worktree per active work package

Following the existing `aN-<slug>` convention from `docs/superpowers/plans/`:

```bash
git worktree add ../DocumentAnalysisMicrosoft-a3-<slug> -b feat/a3-<slug> main
```

One worktree per concurrent feature, not one per Claude. Each Claude `cd`s into
the worktree it should work on.

### 3. Bootstrap each worktree

Worktrees do **not** inherit gitignored files. Per-worktree, you typically need:

- `.env` — copy from the main checkout if the work needs it.
- `.venv` — either run `bash bootstrap.sh` to create a fresh venv, or share the
  main checkout's venv via a settings-level symlink:

  ```json
  // .claude/settings.json
  { "worktree": { "symlinkDirectories": [".venv"] } }
  ```

  Sharing the venv saves disk; recreating it gives true isolation. We default to
  sharing because dependency drift between worktrees is rare.

### 4. Start Claude in the worktree

```bash
cd ../DocumentAnalysisMicrosoft-a3-<slug>
claude
```

The session is fully independent of any other `claude` running in another
worktree.

### 5. Optionally spawn teammates inside that session

Once the experimental flag is active, ask the lead Claude to spawn a teammate
("spawn a teammate to review the test coverage on this branch"). Cycle between
in-process teammates with Shift+Down, or split-pane via tmux/iTerm2.

## Cleanup

When a feature merges to `main`:

```bash
git worktree remove ../DocumentAnalysisMicrosoft-a3-<slug>
git branch -d feat/a3-<slug>
```

`git worktree list` shows what's currently checked out.

## Caveats

- Experimental: known rough edges around session resume and task-status
  tracking. Don't rely on resuming a teammate session across machine restarts.
- Two `claude` sessions in the **same** checkout will collide. Always isolate
  via worktree before running parallel sessions.
- The flag is read at session start; toggling it mid-conversation does nothing.
- Plans and specs continue to live at
  `docs/superpowers/{plans,specs}/YYYY-MM-DD-<aN>-<slug>{,-design}.md`. The
  worktree name should match the plan slug for easy mental mapping.

## Decision log

- 2026-04-29: enabled `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in
  `.claude/settings.local.json`. Reason: experiment with parallel feature work
  after a1/a2 merged. Owner: ktazefid.
