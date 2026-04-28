# Goldens Restructure — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the three existing feature packages into the new
four-layer directory structure (`pipelines/`, `evaluators/`) without
changing any runtime behaviour, then delete the now-obsolete
`curate.py` and its tests.

**Architecture:** Three `git mv` operations + three deletions
(`curate.py`, `test_curate.py`, the `curate` CLI subcommand) +
configuration updates (`bootstrap.sh`, `Makefile`, boundary check
script, READMEs). Python import names (`query_index`, `ingestion`,
`query_index_eval`) stay stable; only directory paths change. After
this plan, `make test` and `make lint` produce the same result as
before, just running against new paths.

**Tech Stack:** Python 3.11, pip-editable installs, ruff, mypy,
pytest, pre-commit, GNU make.

**Spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md`
(§7 Phase 0).

**Scope deviations from spec, agreed during plan-writing:**

1. The `clients/` sub-package split inside `pipelines/microsoft/`
   is deferred to Phase A.1. Phase 0 moves the whole `query-index`
   package as-is.
2. `datasets.py` and `schema.py` in `query-index-eval` are kept
   intact in Phase 0 (still needed by `runner.py`); only `curate.py`
   is deleted.
3. Python import names stay stable in Phase 0; renames are deferred.

These have been reflected in the spec.

---

## File Structure (after Phase 0)

```
features/
├── pipelines/
│   └── microsoft/
│       ├── retrieval/                    ← was features/query-index/
│       │   ├── pyproject.toml
│       │   ├── README.md
│       │   ├── src/
│       │   │   └── query_index/          ← package name unchanged
│       │   └── tests/
│       └── ingestion/                    ← was features/ingestion/
│           ├── pyproject.toml
│           ├── README.md
│           ├── src/
│           │   └── ingestion/            ← package name unchanged
│           └── tests/
└── evaluators/
    └── chunk_match/                      ← was features/query-index-eval/
        ├── pyproject.toml
        ├── README.md
        ├── src/
        │   └── query_index_eval/         ← package name unchanged
        │       ├── __init__.py
        │       ├── cli.py                ← `curate` subcommand removed
        │       ├── datasets.py           ← kept (used by runner)
        │       ├── metrics.py            ← kept
        │       ├── runner.py             ← kept
        │       └── schema.py             ← kept (metrics types)
        └── tests/                        ← test_curate.py removed
```

Files modified at the repo root:

- `bootstrap.sh` — three install paths updated
- `Makefile` — no path-specific targets to update (uses `features/`
  prefix only); verify and adjust if needed
- `scripts/check_import_boundary.sh` — three regex paths updated
- `README.md` — path references updated
- `.pre-commit-config.yaml` — no path-specific patterns to update;
  verify
- The three `features/*/README.md` — path references updated

---

## Task 0: Pre-flight Baseline

**Files:** None (verification only)

- [ ] **Step 1: Activate venv**

```bash
source .venv/bin/activate
```

- [ ] **Step 2: Capture baseline test results**

Run: `make test 2>&1 | tee /tmp/phase0-baseline-tests.log`

Expected: passing test count printed at the end (e.g.
`195 passed in 12.3s`). Record the exact number — this is the bar
the restructure must match.

- [ ] **Step 3: Capture baseline lint state**

Run: `make lint 2>&1 | tee /tmp/phase0-baseline-lint.log`

Expected: clean output (no ruff or mypy errors). If anything is
already failing, stop and surface it before starting the restructure.

- [ ] **Step 4: Confirm clean working tree**

Run: `git status`

Expected: `nothing to commit, working tree clean`. If not, ask the
user before proceeding — Phase 0 should start from a clean baseline.

- [ ] **Step 5: Confirm we are on a fresh branch**

Run: `git rev-parse --abbrev-ref HEAD`

If the branch is `main` or any unrelated feature branch, create the
work branch:

```bash
git checkout -b feat/phase-0-restructure
```

If already on `feat/phase-0-restructure` or another descriptive
restructure branch, continue.

---

## Task 1: Move `query-index` → `pipelines/microsoft/retrieval/`

**Files:**
- Move: `features/query-index/` → `features/pipelines/microsoft/retrieval/`
- Modify: `bootstrap.sh`

- [ ] **Step 1: Create the parent directories**

```bash
mkdir -p features/pipelines/microsoft
```

- [ ] **Step 2: Move the package with `git mv`**

```bash
git mv features/query-index features/pipelines/microsoft/retrieval
```

`git mv` preserves history; do not use plain `mv`.

- [ ] **Step 3: Verify the move**

Run: `ls features/pipelines/microsoft/retrieval/`

Expected output includes: `pyproject.toml  README.md  src  tests`.

- [ ] **Step 4: Update `bootstrap.sh` install path**

In `bootstrap.sh`, change:

```bash
if [ -f features/query-index/pyproject.toml ]; then
    pip install -e features/query-index
fi
```

to:

```bash
if [ -f features/pipelines/microsoft/retrieval/pyproject.toml ]; then
    pip install -e features/pipelines/microsoft/retrieval
fi
```

- [ ] **Step 5: Reinstall the package at its new location**

```bash
pip install -e features/pipelines/microsoft/retrieval
```

Expected: `Successfully installed query-index-...` (the dist name
may still read `query-index`; that is fine, only the path moved).

- [ ] **Step 6: Run the package's tests**

```bash
pytest features/pipelines/microsoft/retrieval/tests -q
```

Expected: same pass count as the baseline portion for query-index
(should match what was previously `pytest features/query-index/tests`).

- [ ] **Step 7: Commit**

```bash
git add bootstrap.sh
git add features/pipelines/microsoft/retrieval features/query-index
git commit -m "refactor(structure): move query-index to pipelines/microsoft/retrieval"
```

The `git add` of both new and old paths captures the rename in one
commit (git's rename detection picks it up).

---

## Task 2: Move `ingestion` → `pipelines/microsoft/ingestion/`

**Files:**
- Move: `features/ingestion/` → `features/pipelines/microsoft/ingestion/`
- Modify: `bootstrap.sh`

- [ ] **Step 1: Move the package with `git mv`**

```bash
git mv features/ingestion features/pipelines/microsoft/ingestion
```

- [ ] **Step 2: Verify the move**

Run: `ls features/pipelines/microsoft/ingestion/`

Expected output includes: `pyproject.toml  README.md  src  tests`.

- [ ] **Step 3: Update `bootstrap.sh` install path**

In `bootstrap.sh`, change:

```bash
if [ -f features/ingestion/pyproject.toml ]; then
    pip install -e features/ingestion
fi
```

to:

```bash
if [ -f features/pipelines/microsoft/ingestion/pyproject.toml ]; then
    pip install -e features/pipelines/microsoft/ingestion
fi
```

- [ ] **Step 4: Reinstall the package at its new location**

```bash
pip install -e features/pipelines/microsoft/ingestion
```

Expected: `Successfully installed ingestion-...`.

- [ ] **Step 5: Run the package's tests**

```bash
pytest features/pipelines/microsoft/ingestion/tests -q
```

Expected: same pass count as baseline ingestion portion.

- [ ] **Step 6: Commit**

```bash
git add bootstrap.sh
git add features/pipelines/microsoft/ingestion features/ingestion
git commit -m "refactor(structure): move ingestion to pipelines/microsoft/ingestion"
```

---

## Task 3: Delete `curate.py` and its CLI surface

**Files:**
- Delete: `features/query-index-eval/src/query_index_eval/curate.py`
- Delete: `features/query-index-eval/tests/test_curate.py`
- Modify: `features/query-index-eval/src/query_index_eval/cli.py`
- Modify: `Makefile` (remove the `curate` target)

- [ ] **Step 1: Delete `curate.py`**

```bash
git rm features/query-index-eval/src/query_index_eval/curate.py
```

- [ ] **Step 2: Delete its test file**

```bash
git rm features/query-index-eval/tests/test_curate.py
```

(If the file does not exist, skip this step. The repo currently has
it.)

- [ ] **Step 3: Remove `curate` references from `cli.py`**

In `features/query-index-eval/src/query_index_eval/cli.py`:

- Delete the import line (~line 17):
  ```python
  from query_index_eval.curate import interactive_curate
  ```
- Delete the `_cmd_curate` function (~lines 78–86).
- Delete the `p_curate = sub.add_parser(...)` block and its
  `p_curate.add_argument` / `p_curate.set_defaults` lines
  (~lines 142–151).

The remaining subcommands (`eval`, `report`, `schema-discovery`)
must continue to register and work.

- [ ] **Step 4: Remove the `curate` Makefile target**

In `Makefile`, delete the lines:

```makefile
curate:
	query-eval curate
```

Also remove `curate` from the `.PHONY:` line and from the `help:`
target's printed list.

- [ ] **Step 5: Reinstall the eval package so the CLI script picks up the change**

```bash
pip install -e features/query-index-eval
```

(Path is still `features/query-index-eval` here; it moves in Task 4.)

- [ ] **Step 6: Verify the CLI no longer offers `curate`**

```bash
query-eval --help
```

Expected: subcommands shown are `eval`, `report`,
`schema-discovery`. No `curate` line. The command exits 0.

Then attempt the removed subcommand:

```bash
query-eval curate
```

Expected: argparse error (`invalid choice: 'curate'`), exit code 2.

- [ ] **Step 7: Run the eval test suite**

```bash
pytest features/query-index-eval/tests -q
```

Expected: passes, with `test_curate.py` no longer collected. The
remaining `test_cli.py`, `test_datasets.py`, `test_metrics.py`,
`test_public_api.py`, `test_runner.py`, `test_schema.py` continue
to pass.

If `test_cli.py` had cases asserting `curate` subcommand behaviour,
remove them as part of this step. (Read it first; only edit if
needed.)

- [ ] **Step 8: Commit**

```bash
git add Makefile features/query-index-eval/src/query_index_eval/cli.py
git add -u features/query-index-eval/
git commit -m "refactor(eval): drop curate.py — replaced in Phase A by event-sourced flow"
```

---

## Task 4: Move `query-index-eval` → `evaluators/chunk_match/`

**Files:**
- Move: `features/query-index-eval/` → `features/evaluators/chunk_match/`
- Modify: `bootstrap.sh`

- [ ] **Step 1: Create the parent directory**

```bash
mkdir -p features/evaluators
```

- [ ] **Step 2: Move the package with `git mv`**

```bash
git mv features/query-index-eval features/evaluators/chunk_match
```

- [ ] **Step 3: Verify the move**

Run: `ls features/evaluators/chunk_match/`

Expected output includes: `pyproject.toml  README.md  src  tests`.

- [ ] **Step 4: Update `bootstrap.sh` install path**

In `bootstrap.sh`, change:

```bash
if [ -f features/query-index-eval/pyproject.toml ]; then
    pip install -e features/query-index-eval
fi
```

to:

```bash
if [ -f features/evaluators/chunk_match/pyproject.toml ]; then
    pip install -e features/evaluators/chunk_match
fi
```

- [ ] **Step 5: Reinstall**

```bash
pip install -e features/evaluators/chunk_match
```

Expected: `Successfully installed query-index-eval-...` (dist name
unchanged; only path moved).

- [ ] **Step 6: Run the moved test suite**

```bash
pytest features/evaluators/chunk_match/tests -q
```

Expected: same pass count as after Task 3.

- [ ] **Step 7: Commit**

```bash
git add bootstrap.sh
git add features/evaluators/chunk_match features/query-index-eval
git commit -m "refactor(structure): move query-index-eval to evaluators/chunk_match"
```

---

## Task 5: Update the import-boundary check

**Files:**
- Modify: `scripts/check_import_boundary.sh`

The script currently allow-lists imports by old path patterns
(`features/query-index/`, `features/ingestion/`). The patterns must
match the new paths.

- [ ] **Step 1: Read the current script**

```bash
cat scripts/check_import_boundary.sh
```

Confirm the two `grep -v` lines reference old paths:

- Line ~28: `| grep -v '^features/query-index/'`
- Line ~41: `| grep -v -E '^features/(query-index|ingestion)/'`

- [ ] **Step 2: Replace the path patterns**

Update the file as follows.

Change the search/openai check (around line 28):

```bash
    | grep -v '^features/query-index/' \
```

to:

```bash
    | grep -v '^features/pipelines/microsoft/retrieval/' \
```

Change the docintel check (around line 41):

```bash
    | grep -v -E '^features/(query-index|ingestion)/' \
```

to:

```bash
    | grep -v -E '^features/pipelines/microsoft/(retrieval|ingestion)/' \
```

Update the comment block at the top of the script (lines 3–10) so
the explanatory text matches:

```bash
# Enforce per-package import boundaries:
#  1. Search & OpenAI imports (azure.search.*, azure.identity.*, openai.*)
#     — only features/pipelines/microsoft/retrieval/.
#  2. Document Intelligence imports (azure.ai.documentintelligence.*)
#     — only features/pipelines/microsoft/retrieval/ OR
#       features/pipelines/microsoft/ingestion/.
```

Also update the two error-message strings (lines 32 and 45) to
mention the new paths:

```bash
echo "BOUNDARY VIOLATION: azure.search.*, azure.identity.*, and openai.* imports are only allowed inside features/pipelines/microsoft/retrieval/"
```

```bash
echo "BOUNDARY VIOLATION: azure.ai.documentintelligence imports are only allowed inside features/pipelines/microsoft/retrieval/ or features/pipelines/microsoft/ingestion/"
```

- [ ] **Step 3: Run the boundary check**

```bash
bash scripts/check_import_boundary.sh
```

Expected: exits 0, prints nothing.

- [ ] **Step 4: Sanity-check by running it through pre-commit**

```bash
pre-commit run import-boundary-check --all-files
```

Expected: `Passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_import_boundary.sh
git commit -m "chore(boundary): retarget import-boundary check to new pipeline paths"
```

---

## Task 6: Update README references

**Files:**
- Modify: `README.md` (repo root)
- Modify: `features/pipelines/microsoft/retrieval/README.md`
- Modify: `features/pipelines/microsoft/ingestion/README.md`
- Modify: `features/evaluators/chunk_match/README.md`

- [ ] **Step 1: Find all old-path references**

```bash
grep -rn "features/query-index\|features/ingestion\|features/query-index-eval" --include="*.md"
```

The matches in `docs/superpowers/specs/` and
`docs/superpowers/plans/` are historical records — DO NOT edit
those. They describe past phases.

The matches in `README.md` (repo root) and the three feature
READMEs ARE updated.

- [ ] **Step 2: Update repo-root `README.md`**

Replace every occurrence of:

- `features/query-index/` → `features/pipelines/microsoft/retrieval/`
- `features/query-index-eval/` → `features/evaluators/chunk_match/`
- `features/ingestion/` → `features/pipelines/microsoft/ingestion/`

If the README has a `## Project layout` or `## Packages` section,
update it to reflect the new tree (mirror the diagram from this
plan's "File Structure" section).

- [ ] **Step 3: Update each feature README**

For each of the three feature READMEs, replace any `features/<old-name>`
self-references with the new path. Update relative paths inside
the README if needed (e.g. links to `../../README.md` may need
adjustment because each package moved deeper into the tree).

- [ ] **Step 4: Verify no stale references remain (excluding spec/plan history)**

```bash
grep -rn "features/query-index\|features/ingestion\|features/query-index-eval" --include="*.md" \
  | grep -v "docs/superpowers/"
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add README.md features/pipelines/microsoft/retrieval/README.md \
        features/pipelines/microsoft/ingestion/README.md \
        features/evaluators/chunk_match/README.md
git commit -m "docs: retarget README path references to new layout"
```

---

## Task 7: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Reinstall everything from a clean state**

```bash
pip uninstall -y query-index ingestion query-index-eval || true
./bootstrap.sh
```

Expected: bootstrap completes, all three editable installs succeed.

- [ ] **Step 2: Full test suite**

```bash
make test
```

Expected: pass count matches the Task 0 baseline minus the
`test_curate.py` cases (those were intentionally deleted in Task 3).
If any unrelated test fails, stop and investigate.

- [ ] **Step 3: Lint**

```bash
make lint
```

Expected: clean (matches Task 0 baseline).

- [ ] **Step 4: Pre-commit on all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass — `import-boundary-check`, `ruff`,
`ruff-format`, `mypy`.

- [ ] **Step 5: CLI smoke test**

```bash
query-eval --help
ingest --help
```

Expected: both print their subcommand listings with no errors.
`query-eval` shows `eval`, `report`, `schema-discovery` (no
`curate`). `ingest` shows `analyze`, `chunk`, `embed`, `upload`.

- [ ] **Step 6: Verify legacy paths are fully gone**

```bash
ls features/query-index features/query-index-eval features/ingestion 2>&1 | grep "No such file"
```

Expected: three `No such file or directory` lines. Confirms nothing
was left behind by the moves.

- [ ] **Step 7: Inspect git log for the phase**

```bash
git log --oneline feat/phase-0-restructure ^main
```

Expected: six commits in this order (subject prefixes may vary
slightly):

1. `refactor(structure): move query-index to pipelines/microsoft/retrieval`
2. `refactor(structure): move ingestion to pipelines/microsoft/ingestion`
3. `refactor(eval): drop curate.py — replaced in Phase A by event-sourced flow`
4. `refactor(structure): move query-index-eval to evaluators/chunk_match`
5. `chore(boundary): retarget import-boundary check to new pipeline paths`
6. `docs: retarget README path references to new layout`

If anything is missing or out of order, ask before squashing or
reordering — historical visibility is part of the value of the
restructure PR.

- [ ] **Step 8: Push and open PR (only if user explicitly approves)**

```bash
git push -u origin feat/phase-0-restructure
gh pr create --title "Phase 0: structural restructure (pipelines/, evaluators/)" \
  --body "$(cat <<'EOF'
## Summary
Pure restructure into the new four-layer layout per
`docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§7 Phase 0).
No behaviour change. `query-eval curate` removed temporarily; replaced
in Phase A.4 by the event-sourced curate flow.

## Test plan
- [ ] `make test` — same pass count as baseline (minus `test_curate.py`)
- [ ] `make lint` — clean
- [ ] `pre-commit run --all-files` — clean
- [ ] `query-eval --help` shows no `curate` subcommand
- [ ] `ingest --help` works

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Pause here for user instruction before pushing or creating the PR.**

---

## Self-Review (filled in by plan author after writing)

**Spec coverage check** — every Phase 0 item from the spec maps to
a task:

| Spec item (§7 Phase 0) | Task |
|------------------------|------|
| Move `features/query-index/` → `pipelines/microsoft/retrieval/` | Task 1 |
| Move `features/ingestion/` → `pipelines/microsoft/ingestion/` | Task 2 |
| Move `metrics.py` → `evaluators/chunk_match/metrics.py` | Task 4 (whole package moved; `metrics.py` is one of its files) |
| Move `runner.py` → `evaluators/runner.py` (or split) | Task 4 (kept as `evaluators/chunk_match/.../runner.py` per agreed deviation) |
| Delete `curate.py`; defer `datasets.py` / `schema.py` | Task 3 (deletions); deferred files explicitly retained |
| Remove `curate` subcommand from CLI | Task 3 (Step 3) |
| `run-eval` and `report` keep working | Task 7 (Step 5 smoke test) |
| Update boundary check | Task 5 |
| Makefile targets updated | Task 3 (Step 4 — `curate` target) plus Task 7 verifies the rest |
| Python import names stay stable | All tasks (no `query_index_eval` → renamed-package work in this plan) |

**Placeholder scan:** No `TBD`, `TODO`, vague hand-waves. Each
step lists the exact command, file path, or edit. The PR-create
step is gated on explicit user approval (per session feedback rule
on visible operations).

**Type-consistency check:** No new types or signatures introduced.
The plan only moves files and edits config; the only edited Python
file is `cli.py`, where the change is a deletion (no new symbols).

**Scope check:** Self-contained — produces working software at the
end (test suite green, CLI working). Phase A.1 (LLM clients) and
Phase A.2+ (`goldens/`) are separate plans, written when Phase 0
lands.
