# Phase 1 plan — Wave 1 (appsec · secrets-crypto-supply · reliability)

Roadmap level: groups and sequences kept findings by type. No per-finding code
steps — that happens at pickup under the implementation gates. Covers only
`keep`/`combine`. `decision-required`/`defer` are recorded in `triage.jsonl` and
get no fix plan here.

Calibrated severity tally (kept work): 1 high · 5 medium · 4 low.

---

## Group g1 — Harden the `pre-bash.py` commit-time backstops (security)

**Findings:** appsec-001 (high), appsec-002 (medium), reliability-003 (low) ·
**File:** `plugins/ca/hooks/pre-bash.py` (~312–377) · **Effort:** S–M

The H-09b/H-10b (crypto/secret) and H-14 (migration) commit backstops share one
weakness class: they scan the **index** (`git diff --cached` / `--name-only`) and
only union worktree state on `-a`/`git add`. Two holes follow:

1. **Pathspec-commit bypass** (appsec-001 crypto/secret, appsec-002 migration):
   `git commit -m x <path>` commits worktree content the index-only scan never
   sees. → When a commit names pathspec tokens (after `--`), union the worktree
   diff/paths (`git diff HEAD [--name-only] -- <paths>`) into the scanned set.
2. **Fail-open on read error** (reliability-003): `added_lines` returns `''` on
   git failure/timeout, so the crypto/secret block silently passes — asymmetric
   with the H-14 sibling, which fails closed. → Distinguish "empty diff" from
   "git read failed" and BLOCK (or fail loud) on the latter, matching H-14.

**Sequence:** fix the shared diff-collection helper once (pathspec union +
read-failure signal), then wire both backstops to it. **Acceptance (rolled up):**
a pathspec-commit of an unstaged crypto/secret change → exit 2 (H-09b/H-10b); a
pathspec-commit of an unstaged migration → exit 2 (H-14); a simulated git-diff
failure on commit no longer silently allows; all existing guard tests still pass.
**depends_on:** none external; appsec-002 & reliability-003 ride on the g1 helper fix.

---

## Group g2 — Close the `_hooklib.py` detection-regex gaps (security)

**Findings:** secrets-001 (medium), secrets-002 (medium) ·
**File:** `plugins/ca/hooks/_hooklib.py` (41–63) · **Effort:** S

The two detection regexes under-match their own policy:

1. **CRYPTO_RE** omits `rc2` and `blowfish` — both in the security-controls.md
   forbidden set. → Add `\brc2\b|\bblowfish\b` (case-insensitive) to the alternation.
2. **SECRET_RE** leading `\b` won't fire inside compound names (`FARM_API_KEY`),
   and the project key prefix `sk-C…` matches none of the high-entropy anchors. →
   Replace the leading `\b` with a start-or-separator anchor so compound keyword
   names trigger; optionally add the project key-format anchor.

**Sequence:** both are one-file edits; do together. **Acceptance (rolled up):**
CRYPTO_RE matches `rc2-cbc` / `new Blowfish(...)`; SECRET_RE matches
`FARM_API_KEY = "sk-real…"`; add matching cases to `.github/scripts/test_hooklib.py`
and confirm the H-09/H-10 integration gates fire (`test_hook_guards.py`). Guards
against future drift.

---

## Group g3 — farm.ts dispatcher robustness (reliability)

**Findings:** reliability-001 (medium), reliability-004 (low) ·
**File:** `plugins/ca/tools/farm.ts` · **Effort:** S–M

Two independent liveness/diagnosability bugs in the dispatcher:

1. **No subprocess timeout** (reliability-001): the shared `run()` helper has no
   kill path, so a hung gate/setup/mutation command wedges a worker slot and the
   scheduler never finalizes. → Add a configurable wall-clock timeout (e.g.
   `FARM_GATE_TIMEOUT_MS`) that kills the child (tree-kill on Windows) and resolves
   as a tagged timeout, mirroring the AbortController already used on the API path.
2. **finally crashes on undefined worktree** (reliability-004): an early setup
   throw leaves `integrationWorktree` undefined; the finally passes it into spawn
   argv → TypeError masks the real error. → Guard the cleanup
   (`if (integrationWorktree) …`) and optionally make `run()` reject non-string argv.

**Sequence:** independent; either order. **Acceptance:** a never-exiting gate
command is killed and surfaces as a gate failure with the scheduler still
finalizing `farm-report.*`; a pre-assignment setup failure surfaces the original
error, not a spawn TypeError.

---

## Group g4 — ca-sandbox build-step failure handling (reliability)

**Finding:** reliability-002 (medium) ·
**File:** `plugins/ca-sandbox/tools/create.ts` (198–228) · **Effort:** S

`defaultBuildImage` ignores the `docker create` and `docker cp` exit codes, so a
partial failure yields an empty checkout, a degenerate dephash, and a wrong/colliding
cache tag — silently. → Check both exit codes; throw (or return a failed
BuildResult) with captured stderr; treat an empty checkout as an explicit error
before `computeDepHash`. The existing `finally` teardown is unchanged.
**Acceptance:** non-zero `docker create`/`cp` aborts with a descriptive error;
no dephash is computed over zero manifests.

---

## Group g5 — H-05 audit-log integrity beyond lexical matching (security)

**Finding:** appsec-003 (low) ·
**File:** `plugins/ca/hooks/pre-bash.py` (72–90, 289–293) · **Effort:** M

The append-only-log guard is purely lexical and evadable via variable indirection
(`$f=overrides.log; rm $f`). → Add a path-aware backstop (PostToolUse check that
the audit logs did not shrink/disappear, or a sanctioned append-only writer); at
minimum extend the accepted-residual-risk note to enumerate variable-indirection
spellings. Lower priority than g1–g4; an unrecoverable control should not rest on
lexical regex alone.

---

## Not planned (recorded in triage.jsonl, no fix this run)

- **secrets-003 → decision-required:** LGPL-3.0-or-later (sharp/libvips) + 0BSD
  (tslib) in `site/package-lock.json` are off the approved-license list. This is a
  governance/ADR-grade license-approval call (like the prior BlueOak/CC0 decision),
  not a fix. → Surface to the user; ADR-stub candidate ("approve LGPL-3.0/0BSD for
  build-time docs-site deps, or add overrides.log entries").
- **secrets-004 → defer:** Math.random for container-name suffixes — not a
  security identifier here; below the issue bar. Preserved, not filed.
