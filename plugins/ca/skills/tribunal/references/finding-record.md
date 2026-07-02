# Finding record — the agent write contract

Every tribunal lens agent emits findings in this format; the orchestrator reads them at triage. This is the only schema an agent needs — triage/run schemas are orchestrator-only (`schemas.md`).

## Write rule

Write each finding as its own file — `findings/<lens>/<finding-id>.json` (e.g. `findings/appsec/appsec-001.json`), one `finding/v1` JSON object per file — in the run directory the orchestrator gives you, the moment it is found. Never a batched write at the end. Durability comes from the one-file-one-finding layout: a process killed mid-write risks only the file being written; every previously written finding is already safe on disk. (There is no append tool; a read-then-rewrite of a shared per-lens jsonl would put the lens's whole findings file at risk on every write — that layout is rejected.)

**Mechanism:** use `Write` only. Never use a Bash shell command to write finding content — arbitrary `evidence` text (quotes, backticks, embedded newlines) will corrupt a shell-escaped write. Never `Write` over an existing finding file. This is safe without locking: you are the only writer under `findings/<lens>/` — no other agent touches your lens's directory.

**Numbering on (re-)dispatch:** before your first write, Glob `findings/<lens>/` — files may already exist if a prior attempt at this lens died partway. Continue numbering from the highest existing `NNN`; never renumber, rewrite, or delete an existing finding file. Prior findings stand; the orchestrator's triage dedups any overlap.

## finding/v1

```json
{"schema":"finding/v1","id":"<lens>-NNN","lens":"<lens>","title":"<imperative,specific>","category":"security|reliability|performance|architecture|observability|maintainability|testing|dependency|migration","severity":"critical|high|medium|low","confidence":0.0,"observed":true,"locations":[{"path":"src/...","lines":"42-58"}],"evidence":"<minimal snippet + 1-2 sentences>","impact":"<what breaks / cost>","recommendation":"<remediation shape, not a patch>","acceptance_criteria":["<verifiable close condition>"],"effort":"S|M|L","depends_on":["<id>"],"dedup_key":"<lens>:<normalized-path>:<slug>","created_at":"<iso8601>"}
```

Minimum required: `locations` (path + lines), `evidence`, `recommendation`. Set `lens` to your own lens name; set `category` to the finding's class, which may differ from your lens (the secrets-supply lens may file a `dependency` finding). `severity`/`confidence` are **provisional** — the orchestrator recalibrates at triage; do not treat your own scores as final. `observed` is `true` when the failure/behavior was directly observed or reproduced (test run, executed path, live config) and `false` when inferred from reading code; triage weighs observed findings above inferred ones at the same confidence.

## id & dedup_key

`id`: `<lens>-NNN`, sequential per lens (`appsec-001`, `appsec-002`, …). `dedup_key`: `<lens>:<path-normalized-to-repo-root>:<short-slug-of-title>` — the orchestrator dedups on this plus overlapping `locations`, and it rides into any filed issue body as a searchable comment.

## Evidence discipline

Concrete `path:line` + minimal snippet on every finding. An absence claim — "no handler", "no teardown", "missing validation" — requires reading the whole relevant unit, never a truncated window.
