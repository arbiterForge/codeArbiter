# Issue filing

Findings become GitHub issues only on explicit selection and authorization. Read the tracker command from `tech-stack.md`; default to `gh issue create` if that is the documented tracker. This lane reruns over time, so filing is **idempotent** — never create a duplicate.

## Selection

File only findings the user explicitly selects ("all keep+combine critical/high", or specific ids). Silence or ambiguity → file nothing. Offer `decision-required` findings as a **separate** opt-in (discussion issues), so design questions don't masquerade as fix tickets.

## What is eligible

`keep` (one issue each) and `combine` groups (one issue per `group_id`), only above the confidence gate (defined in `triage.md`). `duplicate` / `false-positive` / `defer` / `accept-risk` / `investigate` never file. `decision-required` files as a discussion/ADR-candidate issue framed as a question — never a fix ticket, and **never by authoring an ADR** (ADRs come only from `/adr`, user-attributed).

## Dedup — before generating any body

1. Skip any finding already carrying an `issue_ref` in `triage.jsonl` (filed on a prior run recorded in this log).
2. For every remaining selected finding, search the tracker for an open issue carrying its `dedup_key` or matching title (e.g. `gh issue list --search "<dedup_key>"`). The `dedup_key` rides in each body as an HTML comment, so it is searchable. If found, skip and record it as a duplicate in the filing report — do not re-file.

## Body — `bodies/<finding-id>.md`, generated lazily, approved-only

```
# <title>

**Severity:** <final_severity>  |  **Confidence:** <final_confidence>  |  **Effort:** <effort>

**Where:** <path:lines, one per line>

**Evidence:** <minimal snippet + what is observed>

**Impact:** <what breaks / what it costs>

**Recommendation:** <remediation shape>

**Acceptance criteria:**
- <verifiable close condition>

<!-- dedup_key: <dedup_key> · finding: <id> -->
```

`decision-required` variant: frame as **Question / Options / Evidence** — the decision and its trade-offs, not a remediation. Anti-slop applies (no em-dash sentence separators, no filler, no fabricated precision).

## Filing procedure

- **Default (no execution):** write `issue-commands.sh` with one line per issue: `gh issue create --title "<title>" --label "<final_severity>" --body-file bodies/<finding-id>.md` (`decision-required` labelled distinctly, e.g. `--label discussion`). Print the list. Stop.
- **On explicit approval:** run each command; capture the issue URL; write it to `triage.jsonl` as `issue_ref`.
- **Report** a table: finding/group id → created URL, or skipped (duplicate), or failed (with the error). Never silently drop a failure.

Findings file as GitHub issues, never `open-tasks.md` — a periodic-review finding must survive PR abandonment.
