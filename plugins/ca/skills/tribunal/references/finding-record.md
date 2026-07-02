# Finding record — the agent write contract

Every tribunal lens agent emits findings in this format; the orchestrator reads them at triage. This is the only schema an agent needs — triage/run schemas are orchestrator-only (`schemas.md`).

## Append rule

Append each finding as one JSON line to `findings/<lens>.jsonl` in the run directory the orchestrator gives you, the moment it is found — never a batched write at the end. A process killed mid-write then loses at most one discardable partial line.

**Mechanism:** you have `Read` and `Write`, not a native append. Read the current `findings/<lens>.jsonl` (treat a missing file as empty), then `Write` the full file back with the new finding line added at the end. Never use a Bash shell command to write finding content — arbitrary `evidence` text (quotes, backticks, embedded newlines) will corrupt a shell-escaped write. This is safe without locking: you are the only writer of `findings/<lens>.jsonl` — no other agent touches your lens's file.

## finding/v1

```json
{"schema":"finding/v1","id":"<lens>-NNN","lens":"<lens>","title":"<imperative,specific>","category":"security|reliability|performance|architecture|observability|maintainability|testing|dependency|migration","severity":"critical|high|medium|low","confidence":0.0,"observed":true,"locations":[{"path":"src/...","lines":"42-58"}],"evidence":"<minimal snippet + 1-2 sentences>","impact":"<what breaks / cost>","recommendation":"<remediation shape, not a patch>","acceptance_criteria":["<verifiable close condition>"],"effort":"S|M|L","depends_on":["<id>"],"dedup_key":"<lens>:<normalized-path>:<slug>","created_at":"<iso8601>"}
```

Minimum required: `locations` (path + lines), `evidence`, `recommendation`. Set `lens` to your own lens name; set `category` to the finding's class, which may differ from your lens (the secrets-supply lens may file a `dependency` finding). `severity`/`confidence` are **provisional** — the orchestrator recalibrates at triage; do not treat your own scores as final.

## id & dedup_key

`id`: `<lens>-NNN`, sequential per lens (`appsec-001`, `appsec-002`, …). `dedup_key`: `<lens>:<path-normalized-to-repo-root>:<short-slug-of-title>` — the orchestrator dedups on this plus overlapping `locations`, and it rides into any filed issue body as a searchable comment.

## Evidence discipline

Concrete `path:line` + minimal snippet on every finding. An absence claim — "no handler", "no teardown", "missing validation" — requires reading the whole relevant unit, never a truncated window.
