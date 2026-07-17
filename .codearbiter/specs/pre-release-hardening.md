# Sprint spec — pre-release-hardening

Date: 2026-07-13
Goal (user): "run through some more open gh issues before we do the next release"
Slug: `pre-release-hardening`
Branch: `feat/pre-release-hardening` (worktree, based on `origin/main` @ 32b116b)

## Intent

Close the open GitHub issues that mean **the gates are not actually enforcing what they claim**,
before the next release cuts. This is an enforcement-integrity sprint, not a feature sprint. Every
item is a bug where a guard can be sidestepped, silently unwired, or silently lost to a race.

## Concurrency context

A Codex CLI session is running concurrently in the main checkout on `feat/pi-support` (ca-pi host
support, ADR-0013 — user-ratified, out of scope here). This sprint runs in an isolated worktree by
user direction. `CLAUDE_PROJECT_DIR` remains pinned to the main checkout, so **every git write in this
sprint passes `git -C <worktree>`**, which `git_cwd()` (`pre-bash.py:263-300`) honors — the workaround
#223 documents, and which Lane A removes the need for.

## In scope

| Lane | Issue | Problem | Resolution |
|---|---|---|---|
| A | #223 | `pre-bash.py` resolves branch guards against `CLAUDE_PROJECT_DIR` (main checkout), not the command's effective cwd; heredoc *bodies* are pattern-matched as if they were commands | cwd/worktree-aware root resolution; narrow the raw-command fallback to shell-consuming heredocs only |
| B | #237 | The H-19 forgery guard's verb list omits interpreters, so `python -c` can hand-write the security-gate marker; the docs claim enforcement the model cannot deliver | Extend the H-19 verb set to interpreters; correct the docs claim |
| C | #271 | `taskwrite.py` does a lock-free RMW on `open-tasks.md` (lost updates, duplicate dotted IDs); `SessionStart` clobbers a repo-global dev marker and writes a false `DEV: exit` | Hoist the `_ledgerlib` OS lock to `_hooklib`; re-read-under-lock CAS in `taskwrite`; session-scope the dev marker |
| D | #265 | The git-hook shim embeds the last-writing plugin's absolute enforcer path and fails **open** when it's missing — uninstall one of two plugins and both hosts silently lose the git-level backstop | `.git/codearbiter-hooksd/<plugin>.path` drop-in dir; shim iterates it; fail **closed**. Requires **ADR-0014** |
| E | harvest | Five PR-304 review findings queued on the board | Close them alongside |

## Out of scope

- **#270** (Codex MCP write-gate bypass) — **deferred by user decision, 2026-07-13.** The agreed
  path-based guard is sound in shape but rests on an `mcp__*` `tool_input` payload schema never
  observed from a live Codex install. Its own session: capture a real payload first, build against it,
  with its own ADR amending ADR-0010's trust model.
- Feature ideas (#247–#253, #38, #80), GTM (#70, #71), run-metrics noise (#246, #200 — left open).
- ADR-0013 / `feat/pi-support` — the concurrent Codex session's work. Untouched.

## Load-bearing design decisions (settled at the spec gate)

**D-1 — #237 is NOT fixed by consumer-side digest recomputation.** The originally-proposed direction
(git-enforce recomputes the digest set so a hand-written marker carries no authority) is **wrong and
was rejected at the gate**. The consumer already derives the sensitive-line set from the diff; if it
also *recomputed* the approved set, coverage would be vacuously true by construction — the gate would
degrade to an mtime check and the existing TOCTOU case (`test_hook_guards.py:331-339`) would pass when
it must block. `line_digest` is a pure public function of a string the forger already holds, so **no
consumer-side recomputation can distinguish a genuine marker from a forged one.**
`security-controls.md:322-329` already concedes this under ADR-0010: the marker is a *cooperative
attestation* whose value is friction and audit trail, not unforgeability. The sprint therefore closes
the **real** hole (the missing interpreter flank in H-19) and makes the **docs stop overselling**
enforcement the model cannot deliver.

**D-2 — markers stay at the main checkout; branch and diff checks follow the worktree.** A linked
worktree has `.codearbiter/` (tracked) but *not* `.codearbiter/.markers/` (gitignored). So H-09b/H-14
must keep reading gate markers from the pinned project root while reading branch/diff state from the
command's effective cwd. This makes intentional and documented what is today accidental
(`pre-bash.py:769,828` read markers from `root`; everything else reads from `cwd`).

**D-3 — the heredoc fix must narrow the fallback, not strip harder.** `pre-bash.py:588-598`
deliberately retains a raw-`cmd` fallback matcher, because a heredoc fed *to a shell* (`bash <<EOF …
git commit … EOF`) genuinely executes its body — ambiguity resolves closed. That fallback is exactly
what makes `gh pr create --body "$(cat <<'EOF' … git commit … EOF)"` trip H-01. Keep the fallback for
**shell-consuming** heredocs; drop it for non-shell consumers. Do not remove it.

**D-4 — #271's lock is necessary but not sufficient; pair it with re-read-under-lock.** `taskwrite.py`
is the only *programmatic* board mutator, but the harvest/decompose paths write `open-tasks.md` with
the host's own Edit/Write tool and will never take a lock. Reading the board **inside** the lock and
re-running the pure transform on fresh text makes an interleaved external edit a detected-loss rather
than a silent clobber, and independently fixes the duplicate-ID mint (`next_seq` then runs on fresh
text). The lock alone would not.

## Build constraints (non-negotiable, from the codebase)

- `core/pysrc/` is the **single source of truth**. `plugins/ca/hooks/` and `plugins/ca-codex/hooks/`
  are byte-identical vendored copies produced by `tools/sync-core.py`. **Never edit a vendored copy** —
  `.github/scripts/test_sync_core.py` fails if you do. Every task: edit `core/pysrc/`, then run
  `python tools/sync-core.py`.
- **Tests import the vendored `plugins/ca/hooks/` copy**, so a core-only edit is not exercised until
  sync runs. Sync before verifying.
- **Stdlib only** (ADR-0004). Tests are stdlib `unittest`. No pytest, no third-party.
- Two test roots: `plugins/ca/hooks/tests/` (`python -m unittest discover`) and `.github/scripts/`
  (standalone scripts). Both are CI gates (`.github/workflows/ci.yml`).
- All git writes use `git -C <worktree>` (see Concurrency context).

## Acceptance criteria

- **AC-1 (#223 worktree)** — a `git commit` executed from a linked worktree on a feature branch is
  judged against **the worktree's** branch, not the main checkout's. The false-negative closes: a
  worktree sitting on `main`/`master` is BLOCKED by H-01 even when the main checkout is on a feature
  branch.
- **AC-2 (#223 heredoc)** — `gh pr create` / `gh issue create` whose heredoc body merely *contains*
  the text `git commit` does **not** trip H-01/H-09b. A heredoc fed to a **shell** containing a real
  `git commit` still BLOCKS.
- **AC-3 (#237 flank)** — `python -c`, `python3 -c`, `node -e`, `perl -e`, `ruby -e`, `sh -c`
  invocations that write a path under `.markers/` matching a gate-marker name are BLOCKED by H-19,
  matching the existing `mv`/`cp`/`tee` flank.
- **AC-4 (#237 docs)** — the `.codearbiter` directory reference no longer claims a hand-written marker
  cannot satisfy a gate. It states what is true: the flanks add friction and an audit trail on the
  cooperative path (ADR-0010); a determined same-user process can still mint one.
- **AC-5 (#271 board)** — two concurrent `taskwrite` mutations both survive: no lost update, no
  duplicate dotted ID. Proven by a contention test in the `_serialize_transactions` idiom
  (`test_ledgerlib.py:192-231`).
- **AC-6 (#271 dev marker)** — a `SessionStart` from session B does **not** clear session A's live dev
  marker and does **not** append a synthetic `DEV: exit` for it. A session clears only its own.
  Degrades safely when no session id is available.
- **AC-7 (#265 shim)** — with two plugins registered, removing one leaves the git-level backstop wired
  to the survivor. With **zero** resolvable enforcers, the shim **blocks** (non-zero), not exit 0.
- **AC-8 (#265 ADR)** — **ADR-0014** records the reversal of the fail-open accept-risk, and the
  `_githooks.py` header block (lines 25-46, the ADR-of-record today) is rewritten to match.
- **AC-9 (harvest)** — the five PR-304 board items close: `_colorlib._read_custom` catches
  `RecursionError`; invalid-hex boundary cases (`#01020`, `#0102030`, `#0102GG`) assert the violet
  fallback; C0/OSC control chars are stripped from `display_model`/`sub_label` before render; the
  `test_ledgerlib` `_serialize_transactions` negative wait is restored; the codex py2-Windows host
  scenario is documented or asserted.
- **AC-10 (suite)** — full CI suite green on the branch: `unittest discover` over
  `plugins/ca/hooks/tests`, every `.github/scripts/test_*.py`, and `tools/sync-core.py --check`.

## Hard-gate surfaces (halt, do not auto-decide)

- ADR-0014 authorship — user attribution required.
- Any change to `security-controls.md` beyond the D-1 docs correction.
- Merge to `main` — `/sprint` opens a PR; the merge is the user's.
