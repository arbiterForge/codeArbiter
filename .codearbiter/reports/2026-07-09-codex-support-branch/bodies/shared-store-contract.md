# [Decision] Coordination contract for two hosts sharing one .codearbiter/ store

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Type:** decision-required (discussion, not a fix ticket)

**Where:**
- `core/pysrc/_hooklib.py:660-693`
- `core/pysrc/_hooklib.py:626-649`
- `core/pysrc/taskwrite.py:1-133`
- `core/pysrc/taskwrite.py:73-120`
- `core/pysrc/session-start.py:446-467`
- `core/pysrc/session-start.py:546-549`
- `core/pysrc/_hooklib.py:660-712`

**Question:**

ADR-0011 advertises one .codearbiter/ store shared by concurrent Claude and Codex sessions, but the coordination is accidental, not designed. Decide the contract.

**Options / considerations:**
- Locking / compare-and-swap on read-modify-write state (taskwrite board lost-updates, reliability-004) vs accept last-writer-wins.
- Record host= attribution in gate-events.log/overrides.log — get_host().name is on the seam at every call site (observability-001).
- Scope repo-global markers (dev-active) per session, or accept cross-session clobber + the synthetic 'DEV: exit' false audit close (reliability-007).

ADR-candidate — resolve via /ca:adr (user-attributed). Not a fix ticket.

<!-- dedup_key: architecture:core/pysrc/_hooklib.py:shared-store-no-concurrency-contract · findings: architecture-007, reliability-004, reliability-007, observability-001 -->
