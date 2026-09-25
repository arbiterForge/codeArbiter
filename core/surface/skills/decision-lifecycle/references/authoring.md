# ADR authoring and acceptance

Load only after `decision-lifecycle` selects an explicitly authorized authoring or
status-transition action. Do not load this procedure for read-only ADR health.
Read `{{PLUGIN_ROOT}}/includes/smarts/decision-log-format.md` before any log append.
A confirmed decision need not be confirmed again unchanged; missing content and
new status transitions still require their existing explicit user authorization.

## Existing-record transitions

For a user-requested stored status change, resolve the exact existing stem first.
Do not create a missing directory, allocate a new number, or author a replacement
Proposed record for that request. Apply only the explicitly authorized transition
under the marker and immutable-record rules below. Acceptance uses the exact
Accepted/Planned binding sequence; a stored status update alone is not evidence.
A health scan never enters this procedure. New-record authoring follows the phases below.

## Pre-flight

Read existing storage before changing it; never guess a path:

- `{{PROJECT_DIR}}/.codearbiter/decisions/` — if present, read the directory and
  its existing records. Unreadable existing storage is a STOP, not an empty index.
  Only an explicitly authorized new-record request may create an absent directory.
  Read-only status and changes to an existing record never create a missing directory.
- For `/adr`: confirm the user explicitly authorized this decision and supplied (or confirmed) its content. An ADR is never authored as the disposition of a routine finding.

## Phase 1 — Index · gate: BLOCK

Scan `{{PROJECT_DIR}}/.codearbiter/decisions/` for existing `NNNN-*.md` ADR files. Record each by **filename stem** (`0014-githook-shim-dropin-fail-closed`), title, and status. Determine the next sequential number (no gaps) for `/adr`; for `/adr-status` this is the working set.

**The stem is the identifier; the number is only a sort key.** Two ADRs may already share a number — this repository holds two numbered 0014 — so a bare number can name more than one document. Index by stem, and never assume `NNNN` resolves to one file until you have checked.

Gate: the existing ADRs are indexed by stem and, for `/adr`, the next number is fixed and **unused** — a number already taken by an existing stem is not available, even for an unrelated decision.

## Phase 2 — Author (/adr) · gate: STOP

Confirm the decision content with the user — context, the decision itself, alternatives, consequences. MUST NOT fill these from inference. Surface any unknown as an inline `[CONFIRM-NN]` placeholder; do not resolve it by guessing.

**Drop the authoring marker first.** The `pre-write`/`pre-edit` hooks block any write to `.codearbiter/decisions/NNNN-*.md` unless a fresh authoring marker is present — that block requires the authorized authoring workflow to arm its own marker. Direct owner routing executes the same `/adr` procedure, not a second authorization path. Immediately before writing, resolve the **same project root as the ADR guards**
using the installed `_hooklib.project_root()` in the current host/session context.
Those guards use `project_root()`, not the general security/migration `marker_root()`;
do not unconditionally climb to the main worktree or use a fresh Git toplevel guess.
Claude's project-directory signal can legitimately name the main checkout while
execution is in a linked checkout; Codex and Pi use their own host resolution.

Use the host's already resolved native Python 3 executable as `PY` in this Bash
form (equivalent native-shell filesystem operations are allowed). Pass the trusted
installed hooks directory, not a project module with the same name. Preserve the
resolved `ADR_MARKER_ROOT` and exact marker path in workflow context for cleanup,
including across separate shell calls. A resolver failure or empty result stops
before any marker write:

```bash
ADR_MARKER_ROOT="$("$PY" -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from _hooklib import project_root; print(Path(project_root()).as_posix())' "{{PLUGIN_ROOT}}/hooks")" || exit 1
[ -n "$ADR_MARKER_ROOT" ] || exit 1
mkdir -p "$ADR_MARKER_ROOT/.codearbiter/.markers"
touch "$ADR_MARKER_ROOT/.codearbiter/.markers/adr-authoring-active"
```

The marker is honored for 30 minutes. Then write `{{PROJECT_DIR}}/.codearbiter/decisions/NNNN-<slug>.md` using the canonical ADR template — `{{PLUGIN_ROOT}}/skills/decision-lifecycle/references/adr-template.md` (the single source of truth for the ADR shape, shared with `decompose`). Author it with `status: proposed`. If this decision supersedes an existing one, set `supersedes:` to that ADR's **full filename stem** — `supersedes: 0014-githook-shim-dropin-fail-closed`, never `supersedes: 0014` — and leave the prior ADR's file untouched (forward-only chain — do not edit it to add a back-reference).

If the new ADR supersedes only *part* of the prior decision, say which part in the body. `supersedes:` names a document, not a clause, so a chain may legitimately fork — two ADRs can each supersede different clauses of one predecessor. That fork is correct and must not be "repaired"; only the prose can carry the scope.

After writing the ADR, append a corresponding entry to the decision log per the format in `{{PLUGIN_ROOT}}/includes/smarts/decision-log-format.md` — `Decided by:` names the user. Status transitions (`proposed → accepted → superseded | rejected`) require explicit user instruction; never advance status on this skill's own judgment.

**`governs:` makes the decision live.** When an ADR names path globs in `governs:`, the post-write
hook surfaces a one-line notice on any Write/Edit touching a matching file — "this file is governed
by ADR-NNNN" — so a recorded decision pushes back at edit time instead of waiting for a checkpoint
sweep. Offer the field whenever a decision constrains identifiable files; omit it for decisions
without a file footprint. Globs are fnmatch-style against repo-relative forward-slash paths.

Once the ADR file and its log entry are written (and any user-instructed status edit is applied), remove the marker at the exact previously resolved path, even if the shell cwd changed. Do not resolve a different root during cleanup; it exists only for one authoring pass:

```bash
rm -f "$ADR_MARKER_ROOT/.codearbiter/.markers/adr-authoring-active"
```

Gate: the ADR file is written with a real `decided-by` user attribution, numbered without a gap, and its log entry is appended. An ADR with no user attribution, or authored as the disposition of a finding, does not pass — STOP.

### Accepted/Planned binding

`accepted` means **Accepted/Planned**. It records the user's governance decision; it does not claim
that any obligation is Implemented or Verified. When the user explicitly authorizes acceptance:

1. Change only the ADR's status fields to accepted. Derive stable, stem-scoped obligations from every
   normative clause in its immutable record, bind each obligation to exact ADR
   text, and obtain independent review that the sealed obligation set is complete.
2. Route through `commit-gate` to commit the accepted ADR and decision-log append. Do not add the
   acceptance binding to that commit: its `source_commit` cannot truthfully name a commit that does
   not exist yet.
3. From that exact commit, hash the committed Git blob bytes and the separately canonicalized
   immutable record: strict UTF-8 with LF-normalized line endings, containing the complete ADR while
   replacing only the recognized status value in the strictly parsed frontmatter `status:` field and
   `## Status` section with fixed sentinels. The two values must agree. All remaining Status prose,
   including approval attribution, stays bound alongside title, date, `decided-by`, supersession,
   governed paths, H1, and every other section. Malformed or duplicate frontmatter, status, or
   headings fail closed. Append one
   `acceptance` event to
   `{{PROJECT_DIR}}/.codearbiter/decisions/adr-lifecycle.jsonl`, then persist that acceptance binding
   in a subsequent commit. The event uses schema `adr-lifecycle/v1` and records `adr` (full stem),
   `recorded_at`, `source_commit`, `blob_sha256`, `body_sha256`, `obligations`,
   `obligations_sha256`, and `obligations_sealed: true`. A second acceptance or baseline binding for
   the same stem is invalid.
4. Preserve **ADR source ancestry** through delivery. Before opening the PR and again before
   its merge offer, follow the finishing skill's `--merge-method` preflight on the exact base/head.
   A source not already in base ancestry requires a true merge commit with `--match-head-commit`;
   squash or rebase would orphan its identity. Missing source ancestry blocks delivery. Never
   rewrite the acceptance binding or rely on deleted branch objects remaining remotely fetchable.

The lifecycle ledger is append-only. A legacy accepted ADR receives a `baseline` with no fabricated
acceptance commit, an `observed_commit` whose Git blob is rechecked as the migration snapshot, an
empty or incrementally mapped obligation list, and
`obligations_sealed: false`; it remains Accepted/Planned. Later delivery evidence appends records:
`implemented` binds one declared obligation to a source commit and relevant input digests;
`verified` additionally binds a unique event ID, explicit proof contract, repository-scoped claim,
producer, command/workflow identity, timezone-aware observation and expiry times, and the same current
inputs. Evidence paths and digests are recomputed from the named Git commit, never trusted from the
caller. A later uniquely identified event may renew expired or changed-input evidence; an append-only
invalidation event may withdraw a prior evidence event. Only a complete,
sealed obligation set with current implementation inputs and fresh verification inputs derives
Implemented or Verified. Changed inputs invalidate the derived state; history is never rewritten.

After acceptance, do not edit any bound ADR content. A later user-authorized stored status transition
may change only the recognized status value in the strictly parsed frontmatter `status:` and
`## Status`; approval prose remains immutable. Supersession remains a forward reference in the new
ADR. The acceptance commit retains the exact original blob while the immutable-record digest proves
every other byte-equivalent field did not change.

## Hard rules

- MUST author an ADR only through this owner's authorized authoring mode with explicit user attribution. MUST NOT author an ADR as the disposition of a routine finding — an out-of-scope finding gets an inline `[NEEDS-TRIAGE]` marker instead.
- MUST NOT record a decision the user did not explicitly make. "Use your best judgment," "I trust you" are declined.
- MUST NOT resolve a `[CONFIRM-NN]` placeholder by guessing. Surface it and stop.
- MUST NOT advance an ADR's status without explicit user instruction.
- MUST NOT report accepted as Implemented or Verified without complete, sealed, current lifecycle evidence.
- MUST NOT rewrite or truncate a committed `adr-lifecycle.jsonl`, create a second binding, or fabricate legacy acceptance evidence.
- MUST NOT edit a prior ADR or a prior decision-log entry to add a back-reference — supersession is a forward-only chain; append a new record whose `supersedes:` names the prior one.
- **The never-edit rule protects decision CONTENT, not identifiers.** Rewriting what was decided corrupts the record; disambiguating *which document a pointer names* repairs it. Maintainer ruling, 2026-07-25: *"the never edit rule is meant to prevent this situation, not prevent this situation from being fixed."* So a correction that is provably identifier-only — a `supersedes:` value changed from a number to the stem it already meant — is permissible, and nothing else about the file is. Any such correction MUST be a single-line diff that alters not one word of any decision, MUST be visible in its own commit, and still requires the maintainer-armed `adr-authoring-active` marker. MUST NOT touch Context, Decision, Alternatives, Consequences, Risks, `status:`, `date:`, `decided-by:`, or `title:` under this allowance.
- MUST NOT number an ADR with a gap, and MUST NOT reuse a number an existing stem already holds — a shared number makes every bare reference to it ambiguous.
- MUST NOT modify any file under `/adr-status` — it is read-only.
- MUST NOT force the `decision-challenger` agent — its dispatch is MAY only.
