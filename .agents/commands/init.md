# /init

## Purpose

Re-run the codeArbiter initialization detection. For repair only — not for routine use. If `CONTEXT.md` (or the equivalent initialization sentinel file) exists but the sentinel marker is missing or corrupt, `/init` offers repair without full re-initialization. If the user wants a full re-initialization (destructive), they must explicitly confirm.

## Usage

```
/init
```

No arguments. This command is invoked when:
- The initialization sentinel is missing from an existing `CONTEXT.md`
- `${PROJECT_ROOT}/.agents/projectContext/` appears partially populated but the system behaves as if uninitialized
- A new AI session cannot locate the project context after a reset

## What Happens

1. codeArbiter reads `CONTEXT.md` (from `AGENTS.md` §1 or the project-level equivalent)
2. Checks for the initialization sentinel string (defined in `AGENTS.md`)
3. **Two paths:**

   **Path A — Sentinel present, context intact:**
   - Reports: "Initialization is complete. Sentinel found. No action needed."
   - Done.

   **Path B — Sentinel missing from existing CONTEXT.md:**
   - Presents two options to the user:
     1. **Restore sentinel only** (non-destructive) — appends the sentinel to the existing `CONTEXT.md` without changing any other content
     2. **Full re-initialize** (destructive) — re-routes to the context-creation workflow from scratch, overwriting `CONTEXT.md`
   - **Waits for user to choose explicitly** — does not proceed without a clear selection
   - If the user chooses option 2 (destructive): confirms a second time ("This will overwrite CONTEXT.md. Confirm?")

   **Path C — CONTEXT.md does not exist:**
   - Reports: "No CONTEXT.md found. This appears to be an uninitialized project."
   - Offers to run the context creation workflow if one exists (e.g., via the `context-creation` skill)
   - Does not proceed without user confirmation

## Hard Gates

- MUST NOT overwrite `CONTEXT.md` without explicit user confirmation (confirmed twice for full re-init)
- MUST NOT run initialization if the sentinel is already present — report clean status instead
- MUST NOT silently pick between restore and re-initialize — always ask the user
- Read-only in Path A — no files modified

## When NOT to Use

- During normal development: this command is for repair only
- If you want to update project context (e.g., add a new tech stack entry): edit `${PROJECT_ROOT}/.agents/projectContext/` files directly via `/feature` or by hand
- If `CONTEXT.md` is intentionally absent (project is not yet initialized): run the project setup flow, not `/init`
