# SMARTS decision-log format

The append-only decision-log entry schema. Loaded only by the skills/agents that WRITE a log line —
`decision-variance`, `decision-lifecycle`, and the `grader`. The six lenses, cell rules, and strength
labels live in [`core.md`](core.md); read that for the scoring itself.

Path: `<project-root>/.codearbiter/decisions/decision-log.md`. **Strictly append-only** — no
edits to a prior entry, ever (not typos, not formatting). Read prior entries; never rewrite them. To
supersede, append a new entry whose `Supersedes:` references the prior one. Traversal is forward-only:
to find whether an entry was superseded, scan forward for a later entry that references it. No
backward `Superseded by:` field is maintained.

Entries are numbered sequentially (`DECISION-0001`, …; no gaps) and separated by `---`:

```markdown
## DECISION-<NNNN> — <Decision ID> — <one-line summary>

**Date:** YYYY-MM-DD
**Status:** accepted | superseded | deferred
**Supersedes:** DECISION-NNNN | none
**Decided by:** <user identifier> | "user during arbitration session" | "User explicitly accepted recommendation as their decision"
**Decision category:** <category>
**Artifact-section-hash:** <SHA-256 of the cited artifact section, heading inclusive, HTML comments stripped — or "n/a">

### Variance summary
- **Artifact position:** [one sentence]
- **Scaffold position:** [one sentence]
- **Status type:** divergent | scaffold-silent | artifact-silent | same-level-conflict-resolution | open-decision-closure

### Decision
[The user's choice. 2–4 sentences. What was decided, not what was discussed.]

### SMARTS rationale
[Which lenses drove it. 2–6 sentences.]

### Implementation implication
[What changes — specific scaffold files, ADRs, or artifact sections to update.]

### Re-evaluation trigger (deferred only)
[The event that should reopen this. Omit unless status is deferred.]

### Resolves same-level conflict between (when applicable)
[Name both conflicting sources. Omit otherwise.]

---
```

**Artifact-section-hash** — record the SHA-256 of the artifact section that defined the artifact's
position at decision time (section heading inclusive to the next same-or-higher heading exclusive,
HTML comments stripped, UTF-8, full 64-char hex). It is `n/a` for `artifact-silent` variances,
open-decision closures, and process decisions with no artifact source. The Phase 1 stale check
recomputes it on later sessions.

**Never:** edit a prior entry; compress multiple variances into one entry; record "no decision
needed"; omit the SMARTS rationale; omit the hash field (write `n/a`, do not drop it); write a
decision the user did not explicitly make.
