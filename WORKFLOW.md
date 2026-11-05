# WORKFLOW.md — Contribution Tracker Agent Onboarding & Execution Guide

This guide is the project's working agreement for agents and contributors. Adapt the framework-specific sections during project setup; do not treat example paths, commands, or decisions as facts until verified in this repository.

---

## 0. Start Here: Establish the Repository State

From the project root:

1. Read `AGENTS.md` and any more-local `AGENTS.md` files that apply to the files you will touch.
2. Check `git status --short --branch`. Preserve all existing user changes and untracked files.
3. Inspect the actual top-level files and directories. Do not assume the template's example structure was created or remains current.
4. Read `docs/design/README.md` if it exists. Enumerate decision files from the index and filesystem; the index can drift.
5. Read the roadmap and active plan only if they exist. Identify the first incomplete phase from its stated exit criteria.
6. Check the project's declared tooling (manifest, project config, CI, or contributor docs) before choosing test, lint, build, or run commands.

**Do not stop just because an optional document, decision, or tool is absent.** Record the gap, determine whether the task depends on it, and ask only when the missing choice materially changes scope, architecture, security, or user experience.

---

## 1. Source of Truth and Decision Boundaries

Use this precedence when guidance conflicts:

1. Explicit current user instruction
2. Current, accepted design decisions and product constraints
3. Active roadmap and plan
4. `AGENTS.md` and this workflow
5. Historical notes, examples, and superseded plans

The repository's actual decision index and files are authoritative; this template's examples are not. Distinguish clearly between:

- **Confirmed**: explicit user choice or accepted decision
- **Observed**: verified from repository state or tool output
- **Proposed**: recommendation not yet approved
- **Open**: unresolved question that blocks or shapes work

Create or update a decision record for a consequential product, architecture, security, persistence, or interface choice. Do not require an ADR for routine implementation details already covered by an accepted decision. Mark replaced decisions/plans as superseded and point to their replacements; do not leave contradictory instructions executable.

---

## 2. Find the Work and Its Scope

For a planned phase or substantial feature:

1. Read the roadmap and locate the first phase whose exit criteria are not verified.
2. Read that phase's active plan and every decision it references. Verify each referenced file exists.
3. Establish the requested change's scope, constraints, acceptance criteria, and out-of-scope items.
4. Inspect relevant code, tests, and neighboring patterns before proposing edits.
5. Identify uncertainty, risks, dependencies, and the smallest useful verification path.

For a small, local fix, use a lightweight checklist or issue description instead of creating a phase plan. Keep planning proportional to risk; do not create ceremony for a trivial change.

### When a plan is needed

Create or update `plans/phase-N-<name>.md` (or the repository's existing plan convention) with:

- Goal and scope, including explicit non-goals
- Acceptance criteria / observable exit criteria
- Relevant decisions and source files
- Ordered implementation steps, with likely files or components
- Tests and other verification commands, chosen from verified project tooling
- Risks, dependencies, unresolved questions, and rollback considerations where relevant
- Progress and next step

A plan is a proposal until accepted when the project or user requires approval. Do not begin substantial or consequential implementation until the user explicitly approves the plan. Inspection, research, and drafting a plan do not require implementation approval. Approval to implement is not approval to commit, push, publish, deploy, or alter unrelated work.

---

## 3. Implement in Small, Traceable Steps

1. Re-check repository status immediately before editing.
2. Follow the smallest existing pattern that satisfies the accepted scope and decisions.
3. Keep changes focused. Do not refactor unrelated code, alter configuration, add dependencies, or change public behavior without need and approval where required.
4. Trace behavior changes to the relevant decision or acceptance criterion. If a new consequential choice emerges, pause that part, describe the options and tradeoffs, and get a decision before proceeding.
5. Update the decision record and plan if an approved choice changes. Do not silently rewrite a decision to make an implementation appear compliant.
6. Preserve secrets and user data. Never add secrets to code, logs, docs, or commits; use the project's documented secret mechanism.
7. Do not commit, push, deploy, publish, or rewrite history unless explicitly requested.

For each implementation step, run the narrowest relevant test or check. If it fails, determine whether the failure is caused by the change, pre-existing state, or environment; report uncertainty rather than claiming success.

---

## 4. Verify the Result

Before calling the work complete:

- Run the relevant tests, linter, type checker, import/parse check, or build using commands verified in this repository.
- Check the actual output and fix failures caused by the change.
- Review the complete diff and `git status`; ensure no unrelated files or generated artifacts were accidentally included.
- For documentation or decision changes, check links, filenames, commands, and cross-document references. Do not claim runtime/test validation for documentation-only work.
- For behavior changes, verify each acceptance criterion and note any that could not be tested.
- Search for stale references when changing paths, interfaces, decisions, commands, or workflow guidance.

If no test framework or command is configured, do not invent one. Use an appropriate available check, state what was and was not verified, and ask whether tooling setup is desired if it blocks confidence.

---

## 5. Keep Project Records in Sync

When work changes project direction or implementation status, update only the relevant records:

- Decision record(s): current choice, status, consequences, and implementation notes
- Decision index: add/remove/rename references to match the actual files
- Roadmap: phase scope and exit criteria, when affected
- Active plan: completion status and next step
- `AGENTS.md`, `WORKFLOW.md`, and `QUICKSTART.md`: only when standing instructions changed

Afterward, search the documentation set for stale paths, commands, filenames, or claims. Mark historical material clearly rather than deleting useful history blindly.

---

## 6. Project-Specific Commands (Fill In After Verification)

Keep this section truthful for the project. Replace placeholders only after inspecting the repository and running the commands successfully. Delete rows that do not apply.

| Purpose | Verified command | Notes |
|---------|------------------|-------|
| Install/setup | `uv sync --all-groups` | `pyproject.toml` |
| Tests | `uv run pytest` | `pytest` |
| Lint/type check | `uv run ruff check .` | `ruff` (if configured) |
| Build/import/parse | `uv run python -m app.main` | FastAPI app |
| Run locally | `docker compose up --build` | `compose.yaml` |

### Framework adaptation notes

This template is framework-neutral, but the project scaffolding script may not be. The current `new_project.sh` scaffold creates Python/Hermes-plugin directories and assumptions. For a different framework, do not treat those paths, dependencies, layer rules, test commands, or example decisions as applicable: adapt the scaffold and generated onboarding documents to the target framework, then verify every command and reference.

---

## 7. Handoff Checklist

Before ending a work session:

- [ ] Plan or task notes accurately reflect completed and remaining work.
- [ ] Relevant verification was run; results and any gaps are recorded.
- [ ] Relevant decisions and onboarding references are synchronized.
- [ ] Diff and repository status were reviewed; user changes were preserved.
- [ ] The next concrete step and any blocker are clear.
- [ ] No commit, push, deployment, or other external action was performed without explicit authorization.

---

## 8. Quick Reference

- **What is the project?** Read `AGENTS.md` and the product-boundary decision if present.
- **What is decided?** Read `docs/design/README.md` and the applicable decision files.
- **What should happen next?** Read the roadmap and active plan if present.
- **What can I run?** Use only commands verified in project config, CI, or contributor docs.
- **What if implementation conflicts with a decision?** Stop the conflicting work, surface the discrepancy, and resolve the decision before proceeding.
- **What if a referenced file is missing?** Confirm via filesystem/index; correct stale references rather than inventing the file.

> Decisions define accepted constraints; plans organize work; code and verification show what was actually delivered. Keep all three aligned, and report evidence rather than assumptions.