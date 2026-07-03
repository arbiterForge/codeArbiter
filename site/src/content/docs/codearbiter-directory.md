---
title: "The .codearbiter/ Directory Reference"
description: "Every file and directory under .codearbiter/, what writes it, what reads it, and what happens if it's deleted."
---

`.codearbiter/` is codeArbiter's project-state store: a root-level directory, outside `.claude/`,
so it survives even if the plugin itself is uninstalled. It holds the project's own record — its
spec, task board, decisions, and audit trail — separate from the plugin code that reads and
writes it. `/ca:init` scaffolds it; `/ca:create-context` (existing codebase) or `/ca:decompose`
(greenfield) populates it. Its presence and content is the plugin's actual contract with your
repo: if you want to know what codeArbiter knows about your project, or what it will do next,
this directory is where to look.

Enforcement itself is gated on one file in here: `CONTEXT.md`. Everything else described below
only matters once that file carries `arbiter: enabled`.

This page documents every file and directory a stock install produces or reads. Some appear only
once the feature that uses them first runs (`.markers/`, `.provenance/`, `spikes/`, `reports/`);
those are noted below.

## At a glance

| Path | Written by | Read by | Editable by hand? |
|---|---|---|---|
| `CONTEXT.md` | `/ca:init`, `/ca:decompose`, `/ca:create-context` | every enforcement hook (`arbiter_active()`), the orchestrator | Yes, but the frontmatter is guarded — see below |
| `open-tasks.md` | `/ca:task` only | `/ca:status`, the statusline, `SessionStart` | No — guarded to `/ca:task` |
| `open-questions.md` | the orchestrator, when a `[CONFIRM-NN]` is raised | `/ca:status`, `SessionStart`, the statusline | Yes |
| `decisions/*.md`, `decision-log.md` | `/ca:adr` only | `/ca:adr-status`, `/ca:reconcile`, `post-write-edit.py` (H-12) | No — guarded to `/ca:adr` |
| `specs/*.md` | `brainstorming` skill (via `/ca:feature`, `/ca:sprint`) | `writing-plans`, `/ca:status` | Yes |
| `plans/*.md` | `writing-plans` skill | `executing-plans`, `subagent-driven-development`, `/ca:status` | Yes |
| `checkpoints/*.md` | `checkpoint-aggregator` agent (`/ca:checkpoint`) | `/ca:audit`, `/ca:status`-adjacent reads | Yes |
| `audits/*.md` | `/ca:audit` | humans (report only) | Yes |
| `reports/<run-id>/` | `/ca:tribunal` | `/ca:tribunal` on resume, the filing gate | Yes, but not while a run is in flight |
| `sprint-log.md` | `/ca:sprint` | `/ca:status`, `/ca:audit` | No — append-only, guarded (H-05) |
| `overrides.log` | `/ca:override`, `/ca:dev` entry/exit | statusline, `/ca:status`, `/ca:audit`, staleness-warn | No — append-only, guarded (H-05) |
| `triage.log` | `/ca:feature` small-lane triage | `/ca:metrics`, `/ca:audit` | No — append-only, guarded (H-05) |
| `gate-events.log` | every `block()`/`remind()`/`warn()` call in the hooks | (durable sink; no reader ships yet) | No — append-only, guarded (H-05) |
| `.markers/` | `security-pass.py`, `migration-pass.py`, `/ca:dev`, `/ca:adr` | the commit-gate hooks (`pre-bash.py`, `pre-write.py`, `pre-edit.py`) | No — guarded, and hand-written markers can't satisfy a gate |
| `.provenance/*.json` | `context-creation`, `decompose`, `context-check` (re-scout/re-baseline) | `SessionStart` (drift line), `commit-gate` (auto-heal) | Not by hand — regenerate via `/ca:context-check` |
| `security-controls.md`, `tech-stack.md`, `coding-standards.md` | `/ca:init` / `/ca:create-context` / `/ca:decompose`, kept current by hand or `/ca:context-check` | every reviewer agent, the crypto/secret gates | Yes |
| `last-checkpoint` | `checkpoint-aggregator` agent | `/ca:status`, the statusline (overrides-since-checkpoint) | Not normally — it's a counter, not a note |
| `spikes/*.md` | `/ca:spike` | humans, `/ca:feature` (seeds `brainstorming`) | Yes |

## CONTEXT.md

The activation contract. Its leading YAML frontmatter carries two load-bearing keys:

- **`arbiter: enabled`** — the single flag every enforcement hook checks via `arbiter_active()`
  (`plugins/ca/hooks/_hooklib.py`). It must appear inside a *properly closed* frontmatter block —
  `---` opens on line 1, `arbiter: enabled` somewhere inside, `---` closes it. A block that opens
  but never closes is treated as **malformed**, not disabled, and is surfaced as an error rather
  than silently ignored. A file with no frontmatter at all is simply dormant. No frontmatter,
  malformed frontmatter, or `arbiter: disabled` all mean: nothing loads, nothing blocks.
- **`stage: N`** — a single maturity number that `/ca:status` and the statusline surface. It has
  no enforcement effect encoded in this file itself; it is a legible signal for how far the
  project has matured, not a config switch.

The body needs an `<!--INITIALIZED-->` marker before the file counts as populated. `SessionStart`
checks for it: present with source code in the repo but the marker absent routes to
`/ca:create-context`; absent with no source routes to `/ca:decompose`. Once the marker and
frontmatter are both in place, the orchestrator persona loads on every session in this repo.

**Writers:** `/ca:init` (scaffold), `/ca:decompose` and `/ca:create-context` (populate + lock).
**Readers:** every enforcement hook, the `SessionStart` injector, the statusline.
**Editable by hand?** The prose body, yes. The frontmatter is guarded: a Write/Edit that would
flip `arbiter: enabled` off, or corrupt the block, is blocked (`pre-write.py`/`pre-edit.py`,
issue #159) — the file that turns every gate off can't itself be edited past the gate.
**Delete it:** codeArbiter goes fully dormant in this repo on the next session — no persona, no
enforcement, nothing loads. The rest of `.codearbiter/` is untouched on disk; recreating
`CONTEXT.md` (or running `/ca:init` again) reactivates it against whatever state remains.

## open-tasks.md

The [board](/glossary/#board): one top-level `- ` bullet per task, in one of three states —
queued (`- [ ]`), in-progress (`- [~]`, always carrying a started date), or done (`- [x]`). The
only sanctioned writer is `/ca:task` (`add` / `start` / `done`), which calls the pure
`_taskboardlib` transforms via `taskwrite.py` so every entry stays schema-conformant and every
transition dated — hand-editing risked malforming the schema, which is why the command exists.
A task's `[x]` done-flip, `[~]` start-flip, or new `[ ]` entry rides the work commit itself
through commit-gate (ADR-0008); there's no separate lagging board-only PR.

**Writers:** `/ca:task` only. **Readers:** `/ca:status`, the statusline, `SessionStart` (in-flight
count and staleness). **Editable by hand?** No — guarded to the one writer.
**Delete it:** the board is empty going forward; nothing else breaks, but every count that reads
it (statusline, `/ca:status`) reports zero until tasks are re-added.

## open-questions.md

The record of unresolved `[CONFIRM-NN]` items — numbered placeholders for a question only the
user can answer, per the terminology lock in `ORCHESTRATOR.md` §0.1. An open `CONFIRM-NN` blocks
stage promotion until it's resolved; it is never guessed at or resolved inside an ADR. The
`SessionStart` hook and the statusline both count occurrences here.

**Writers:** the orchestrator, when a skill surfaces a genuine unknown. **Readers:** `/ca:status`,
`SessionStart`, the statusline. **Editable by hand?** Yes — resolving a `CONFIRM-NN` is a prose
edit recording the decision and its date. **Delete it:** any `[CONFIRM-NN]` count in the
statusline or `/ca:status` reads zero; a future skill that needs to raise one recreates the file.

## decisions/

One numbered, dated, user-attributed file per Architecture Decision Record (`0001-*.md`,
`0002-*.md`, …), plus `decision-log.md`, an append-only ledger that mirrors every ADR as one
entry. `/ca:adr` is the only sanctioned author; both the shell flank (redirects, `cp`, `sed -i`
targeting `decisions/`) and the Write/Edit flank are guarded (H-11) so an ADR can't be
fabricated, edited after the fact, or slipped in outside the command. Status moves through
`proposed -> accepted -> superseded | rejected`; a superseding decision never rewrites the prior
file — it appends a new numbered ADR whose own text names what it supersedes, and a new
`decision-log.md` entry does the same.

**Writers:** `/ca:adr` (via the `decision-lifecycle` skill) only. **Readers:** `/ca:adr-status`,
`/ca:reconcile`, and `post-write-edit.py`'s H-12 advisory (a file matching an ADR's `governs:`
glob gets a reminder on every future touch). **Editable by hand?** No — guarded.
**Delete it:** the project's decision history is gone; `governs:` reminders for any ADR that used
to cover a file stop firing, and `/ca:adr-status` has nothing to report.

## specs/

One markdown file per feature/campaign spec, written by the `brainstorming` skill once a spec is
approved (`/ca:feature`, `/ca:sprint`). `writing-plans` reads an approved spec to derive its task
plan, and `/ca:status` lists every slug here alongside its plan to show how far each pipeline got.

**Writers:** `brainstorming`. **Readers:** `writing-plans`, `/ca:status`.
**Editable by hand?** Yes — specs are prose documents; edit for clarity, but avoid rewriting
acceptance criteria the plan and its tests already trace against.
**Delete it:** `/ca:status` no longer lists that pipeline; a plan that referenced the missing spec
still runs (the plan is self-contained), but nothing can re-derive it from the (now-gone) spec.

## plans/

One markdown file per feature's task plan, written by `writing-plans` from an approved spec.
Each task carries an exact file path and a verification step that maps to a `tdd` obligation.
`executing-plans` and `subagent-driven-development` consume it task by task; `/ca:status` reports
the ACCEPTED-vs-total count for an in-progress plan.

**Writers:** `writing-plans`. **Readers:** `executing-plans`, `subagent-driven-development`,
`/ca:status`. **Editable by hand?** Yes, though editing mid-execution risks desyncing the
plan from tasks already marked accepted. **Delete it:** an in-progress feature loses its
resumption point; `/ca:status` can no longer report that pipeline's progress.

## checkpoints/

One dated report per `/ca:checkpoint` sweep (`YYYY-MM-DD.md`), written by the
`checkpoint-aggregator` agent from the finding-triage and decision-challenger output. Findings are
classified by severity; the ones blocking the current change are called out, the rest recorded
for later. `/ca:tribunal`'s deep-audit output is a distinct artifact (`reports/<run-id>/`, below)
— checkpoints are the lean, routine sweep.

**Writers:** `checkpoint-aggregator`. **Readers:** humans (the report is the deliverable);
`/ca:audit` pulls still-open findings from the most recent one. **Editable by hand?** Yes, though
there's rarely reason to. **Delete it:** history of past sweeps is gone; the next `/ca:checkpoint`
recreates the directory and writes fresh.

## audits/

One dated governance packet per `/ca:audit` run (`YYYY-MM-DD.md`), assembling commits, overrides,
ADRs, sprint auto-decisions, open questions, and open checkpoint findings for a given range into
one document. `/ca:audit` is read-only against everything it summarizes — it never mutates
`overrides.log`, `decisions/`, or any of its other sources.

**Writers:** `/ca:audit`. **Readers:** humans. **Editable by hand?** Yes.
**Delete it:** past audit packets are gone; nothing else in the framework depends on their
presence, since `/ca:audit` re-derives everything from the underlying logs and files each run.

## reports/

`/ca:tribunal`'s working directory: `.codearbiter/reports/<run-id>/`, where `<run-id>` is
`<UTC-date>-<scope-slug>`. A fresh run creates the directory and opens `run.jsonl`; a resumed run
reuses the same `run-id` (the date is the run's creation date and never changes on resume). Every
lens's findings are written one file per finding, plus append-only triage/run logs, so an
interrupted deep audit picks back up from disk instead of restarting. Tribunal writes are confined
to this directory until the filing gate — it never edits, refactors, or commits project code.

**Writers:** `/ca:tribunal` only. **Readers:** `/ca:tribunal` itself, on resume, and the filing
gate that turns approved findings into GitHub issues. **Editable by hand?** Not while a run is
in flight — you'd desync the resumable state. **Delete it:** an in-flight tribunal run can no
longer resume and restarts from scratch on next invocation; completed runs' local record is gone
(filed GitHub issues, if any, are unaffected — they live on GitHub, not here).

## sprint-log.md

The append-only ledger of every SMARTS-scored auto-decision an autonomous `/ca:sprint` makes on a
non-hard-gate point, each entry carrying a confidence flag (`low` entries are the ones worth
reviewing after the fact). Hard gates — security controls, auth/crypto/secrets, irreversible
operations, an unresolved `[CONFIRM-NN]`, a merge to default — are never auto-decided and never
appear here as a resolved decision; they stop and surface to the user instead.

**Writers:** `/ca:sprint`. **Readers:** `/ca:status`, `/ca:audit`, the staleness-warn check (a
sprint marked active for over 30 minutes with no matching log activity gets a WARN).
**Editable by hand?** No — one of the four append-only audit logs (H-05): a shell truncation/
rewrite aimed at it is blocked, and a Write/Edit must be a verifiable tail-anchored append, never
an overwrite or an empty-`old_string` edit passed off as one.
**Delete it:** the sprint decision trail for past runs is gone; a `/ca:sprint` in progress that
depended on it for staleness-warn context loses that signal, though the sprint itself can still
recreate the file on its next append.

## overrides.log

The append-only, permanent audit trail of every `/ca:override` bypass and every `/ca:dev`
entry/exit. Format: `[ISO-8601] | BY: <name> <<email>> | GATE: <gate bypassed> | REASON: <reason>`.
The operator identity comes from `git config user.email`; if it's unset, the user is asked once
rather than recording an empty `BY:` field. The statusline counts entries newer than the
`last-checkpoint` marker as "overrides since last checkpoint."

**Writers:** `/ca:override`, `/ca:dev` (entry/exit lines). **Readers:** statusline, `/ca:status`,
`/ca:audit`, the CONFIRM-09 staleness-warn check. **Editable by hand?** No — H-05 guarded, same as
`sprint-log.md`: append-only, tail-anchored edits only, no truncation or rewrite.
**Delete it:** the entire override history is gone — a genuine loss, since this is the one
mechanical record that a bypass happened at all. codeArbiter keeps functioning; the audit trail
does not recover.

## triage.log

The append-only record of every small-lane classification `/ca:feature` makes (the SMARTS
reasoning behind routing a change to the lighter lane instead of the full spec-to-plan pipeline).
`/ca:metrics` reads it to compute the small-lane rate trend.

**Writers:** `/ca:feature` (small-lane triage step). **Readers:** `/ca:metrics`, `/ca:audit`.
**Editable by hand?** No — H-05 guarded, same append-only contract as the other three logs.
**Delete it:** the small-lane classification history is gone; `/ca:metrics`' small-lane-rate trend
has nothing to compare against until new entries accumulate.

## gate-events.log

The durable, mechanical sink every `block()`, `remind()`, and `warn()` call in the hooks appends
one line to — `[ISO-8601Z] KIND [tag] hook=<script> | msg`. Before this log existed, a gate
decision was visible only in the ephemeral per-turn stderr transcript; this makes every BLOCK,
REMIND, and WARN durable and queryable after the fact. The write is fail-open by contract: a
missing `.codearbiter/` directory or an unwritable log file is swallowed silently rather than
changing the calling hook's exit code — this sink must never itself cause a gate to misbehave.

**Writers:** every hook, via the shared `_log_gate_event()` helper in `_hooklib.py`.
**Readers:** none ship yet as of this writing — it's a durable record for manual inspection or a
future consumer. **Editable by hand?** No — H-05 guarded, same append-only contract.
**Delete it:** past gate decisions are gone from the durable record; hooks keep blocking/reminding
exactly as before (the log is a side effect of a gate decision, never a precondition for one), and
a fresh file is created on the next event.

## .markers/

Gate-pass tokens and short-lived UI flags, created on demand — this directory doesn't exist until
the first marker-writing action runs. The load-bearing ones:

- **`security-gate-passed`** — written by `security-pass.py` on a genuine crypto-compliance or
  secret-handling PASS. It contains a SHA-256 digest of every sensitive added line it approved,
  not just an empty touch. The commit-time gates (**H-09b** for crypto/TLS, **H-10b** for secrets)
  block a commit unless this marker is **fresh** (written within the last 30 minutes) **and**
  covers every sensitive line in the current staged diff — a pass recorded for one diff can't
  launder a later, different change through the freshness window.
- **`migration-gate-passed`** — the same digest-binding contract, for the H-14 migration-review
  gate, written by `migration-pass.py` against a migration file's current content.
- **`dev-active`** — a gitignored flag dropped on `/ca:dev` entry and removed on `/ca:arbiter`
  exit; purely a statusline/UI signal, not itself gate-bearing.
- **`adr-authoring-active`** — touched by `/ca:adr` while an ADR authoring session is open; the
  one marker a command other than the security-pass helpers legitimately writes directly.

**Writers:** `security-pass.py`, `migration-pass.py`, `/ca:dev`, `/ca:adr`.
**Readers:** the commit-gate hooks (`pre-bash.py`) that check `security-gate-passed` and
`migration-gate-passed` before allowing a `git commit`.
**Editable by hand?** No, and a hand-written marker can't satisfy a gate anyway — `pre-write.py`
and `pre-edit.py` block Write/Edit targeting this directory (issue #160), because a load-bearing
marker that turns a BLOCK into an allow must only ever come from the process that actually ran the
check.
**Delete it:** every commit-time crypto/secret/migration gate reverts to its unpassed state — the
next sensitive commit blocks until the corresponding gate runs again and re-records a pass. No
enforcement is weakened; you just lose the standing "already checked" credit.

## .provenance/

Per-doc JSON evidence files (`<doc>.json` — `tech-stack`, `coding-standards`,
`security-controls`, `CONTEXT`, and similar derived docs), created the first time
`context-creation` or `decompose` populates `.codearbiter/`. Each record lists the source paths
that backed the doc's claims, a content hash per path (via `git hash-object`, so a line-ending
normalization never false-flags as drift), and the specific claim each source line supports.
`SessionStart` diffs the recorded hashes against the current ones and surfaces a one-line drift
count when a tracked source has moved since the doc was last baselined; commit-gate can auto-heal
the affected doc from there.

**Writers:** `context-creation`, `decompose`, and `context-check`'s re-scout/re-baseline actions.
**Readers:** `SessionStart` (the drift line), commit-gate (auto-heal worklist).
**Editable by hand?** Not usefully — a hand-edited hash wouldn't match anything real. Regenerate
it through `/ca:context-check` instead. **Delete it:** drift detection goes silent for every doc
that lost its record — no false positives, but no warning either, until the doc is re-scouted or
re-baselined and a fresh provenance file is written.

## Other scaffold docs

`security-controls.md`, `tech-stack.md`, and `coding-standards.md` round out the scaffold `/ca:init`
produces. They're living reference documents, not audit logs — hand-editable, read by every
reviewer agent (`security-controls.md` especially: the crypto-compliance and secret-handling gates
read it before every review, and it's level 1 in the conflict hierarchy). `last-checkpoint` is a
one-line counter (the override count at the time of the last `/ca:checkpoint`) that the statusline
and `/ca:status` use to compute "overrides since last checkpoint" — it's a counter, not a note, so
there's rarely reason to hand-edit it. `spikes/` holds one findings file per `/ca:spike` — the
question asked, what was tried, the answer, and what it implies — written on exit, since spike code
itself is disposable and never merges.
