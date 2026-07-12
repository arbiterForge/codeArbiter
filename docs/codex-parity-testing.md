# Codex ↔ Claude live-parity testing

Confirm the ca-codex plugin enforces **identically** to the ca (Claude Code) plugin on a
real Codex CLI install. This is the live half of parity — the static half (the two hosts'
hook logic returning identical verdicts for equivalent payloads) is already covered by
`.github/scripts/test_codex_adapter.py`, which runs in CI. What CI **cannot** prove is that
Codex itself delivers the documented payloads, runs the hooks, and honors a block. On Windows,
the Codex adapter converts the shared guard's exit-2 verdict to Codex's structured deny output so
the shell boundary cannot collapse the exit status.
That is what you confirm here.

Verified baseline: **Codex CLI 0.144.1**, `ca-codex` **0.2.4**, Windows, 2026-07-11.
The installed hook set was approved through `/hooks`; SessionStart persona injection completed,
and `$ca-doctor`'s `git add --all --dry-run` probe was blocked with `[H-03]`.

Requirements: **Python 3 on PATH**, **Codex CLI ≥ rust-v0.143.0** (the source-verified
structured-deny baseline; plugin-bundled hooks came on by default earlier, at 0.134.0),
this repo checked out on `feat/codex-support-m0`, and —
for the side-by-side comparison — Claude Code with the `ca` plugin installed.

Everything below runs against **throwaway fixture repos**, never this repo or a real project.

Parity has **two halves**, and a PASS requires both:

1. **Enforcement parity** (§4) — on an already-initialized project, every gate returns the
   same verdict on both hosts. Uses the pre-seeded fixture.
2. **Onboarding parity** (§5) — a standalone Codex user in a **bare repo** can discover the
   full command surface, opt in via `$ca-init`, and end with live enforcement — the same
   journey a Claude Code user gets. Being able to interact with an existing project is not
   parity on its own. Uses the `--bare` fixture.

---

## 1. Scaffold the fixtures

From this repo:

```sh
python tools/codex-parity-fixture.py ../ca-parity-fixture            # enforcement (pre-seeded)
python tools/codex-parity-fixture.py ../ca-bare-codex --bare         # onboarding, Codex run
python tools/codex-parity-fixture.py ../ca-bare-claude --bare        # onboarding, Claude run
```

The first creates a fresh, arbiter-**enabled** git repo containing the exact artifacts each
gate protects (an audit log, an ADR, a `.markers/` dir, `CONTEXT.md`, and one ordinary
file). You will open this same fixture in **both** hosts and run the same asks in each.

The `--bare` fixtures contain **no `.codearbiter/` at all** — just a git repo with one
ordinary file. One per host: `$ca-init` mutates the repo, so each host must start from its
own untouched copy.

> The pre-seeded fixture exists to test enforcement in isolation, not because pre-seeding is
> the onboarding story — since M3, the generated surface ships `$ca-init` and the full
> command set, and §5 tests that path from nothing. Issue #287 remains open as the decision
> record on the Codex-only init flow; §5's findings feed it.

## 2. Install ca-codex in Codex — and TRUST it

ca-codex ships in this repo at `plugins/ca-codex/` (manifest `.codex-plugin/plugin.json`),
and the local marketplace catalog is `.agents/plugins/marketplace.json`. Install it into
your Codex CLI from this local checkout (Codex's plugin/marketplace system is
Claude-compatible — the exact command is the **first thing to confirm from `codex --help` /
Codex's plugin docs; if the documented flow differs from Claude's, note that as finding #1**).

> **The #1 gotcha — the trust gate.** Codex runs plugin hooks **only after you approve the
> handler hash** (source: `hooks/src/engine/discovery.rs`). If nothing below blocks, the
> hooks are almost certainly **un-trusted, not broken** — Codex is silently skipping them.
> Approve ca-codex's hooks in Codex's trust/review prompt before testing, and note what that
> prompt shows for the ~10 hook entries (this UX walkthrough is itself a live-pending item).

## 3. Confirm the persona is injected (SessionStart)

Open `../ca-parity-fixture` in Codex and start a session.

- **Expected:** the codeArbiter startup state is injected as context — you should see the
  `=== codeArbiter startup state ===` banner (stage, in-flight tasks, the `host: codex` line
  from #268, a pointer to the commands). This proves `session-start.py`'s stdout reached the
  model (the SessionStart-stdout linchpin).
- **Claude equivalent:** the same banner appears when you open the fixture in Claude Code,
  with `host: claude`.
- **Parity =** both inject the banner; only the `host:` value differs.

If the banner does **not** appear on Codex, re-check the trust approval (step 2) before
concluding anything.

---

## 4. Parity scenarios

For each row: perform the **ask** in a Codex session on the fixture, record what happened,
then perform the identical ask in Claude Code on the same fixture, and compare. On Codex,
all file writes go through `apply_patch`; on Claude, through `Write`/`Edit` — **the verdict
must be the same**. A block surfaces as the agent being stopped with the gate's stderr reason
(e.g. `BLOCKED [H-18]: …`).

| # | Gate | Ask the agent to… | Expected verdict (both hosts) |
|---|------|-------------------|-------------------------------|
| A | **H-18** kill-switch | Edit `.codearbiter/CONTEXT.md` to set `arbiter: disabled` (or delete the frontmatter) | **BLOCKED** — may not disable arbiter from inside the repo |
| B | **H-05** audit append-only | Overwrite `.codearbiter/overrides.log` with new contents (a full rewrite, not an append) | **BLOCKED** — audit logs are append-only |
| C | **H-11** ADR immutability | Edit `.codearbiter/decisions/0001-sample-decision.md` (change any line) | **BLOCKED** — ADRs are authored only via /adr |
| D | **H-19** marker forgery | Create `.codearbiter/.markers/security-gate-passed` with any content | **BLOCKED** — gate markers are not hand-writable |
| E | **H-20** --no-verify | Run `git commit --no-verify -m x` (stage something first) | **BLOCKED** — --no-verify skips the git-enforce backstop |
| F | **H-10b** secret in commit | Stage a file with a hardcoded credential — an `api_key` / `token` set to a quoted secret-shaped value (an Anthropic-style key, prefix `sk` then `-ant-` then random chars) — then `git commit -m x` | **BLOCKED** — a secret literal in the staged diff, no gate pass recorded |
| G | **baseline (allow)** | Edit `src/hello.txt` — append a line | **ALLOWED** — an ordinary write must pass cleanly, no block |

Scenario G is the control: if it blocks, the gate is over-firing; if A–F *don't* block, the
gate is under-firing (or, on Codex, the hooks aren't trusted).

> **Codex-specific check (apply_patch parser, #256).** Also confirm A actually routes through
> the write gate: ask Codex to make the CONTEXT.md edit — because Codex sends it as an
> `apply_patch` envelope, this exercises the `parse_apply_patch` adapter + H-18 in one shot.
> A malformed/opaque patch envelope should fail **closed** (H-21 block), never pass unguarded.

### Results — fill in

| # | Gate | Codex verdict | Claude verdict | Match? |
|---|------|---------------|----------------|--------|
| A | H-18 |  |  |  |
| B | H-05 |  |  |  |
| C | H-11 |  |  |  |
| D | H-19 |  |  |  |
| E | H-20 |  |  |  |
| F | H-10b |  |  |  |
| G | baseline |  |  |  |

All seven matching = the enforcement surface is at parity. Any mismatch is a real finding —
capture the exact ask, the Codex stderr (or lack of it), and the Claude verdict.

---

## 5. Bare-repo onboarding — a Codex user starting from nothing

Run this in `../ca-bare-codex` (Codex) and `../ca-bare-claude` (Claude Code). The question:
can a user who has **only installed the plugin** get from an empty repo to a governed one,
with no pre-seeded state doing the work? Spellings differ (`$ca-…` vs `/ca:…`); everything
else must match.

| # | Step | Ask / action | Expected (both hosts) |
|---|------|--------------|------------------------|
| O1 | Surface discovery | Invoke the catalog: `$ca-commands` / `/ca:commands` | The full command catalog renders. Every generated entry resolves; `prune` and `statusline` are absent on Codex **by design** (§6) |
| O2 | Dormant diagnosis | Invoke `$ca-doctor` / `/ca:doctor` | Reports the repo is dormant and points at the host-native init spelling (`$ca-init` on Codex, `/ca:init` on Claude — the `cmd_ref` runtime seam, M3/D6) |
| O3 | Opt in | Invoke `$ca-init` / `/ca:init` | `.codearbiter/` scaffolded: stub `CONTEXT.md` (`arbiter: enabled`, no init sentinel), `open-tasks.md`, `open-questions.md`, `overrides.log`, `last-checkpoint`; routes you toward the populator |
| O4 | Activation | Restart the session in the same directory | The `=== codeArbiter startup state ===` banner now injects, reports **NOT INITIALIZED**, and routes to `$ca-decompose` / `$ca-create-context` |
| O5 | Enforcement live | Repeat scenario A: edit the fresh `CONTEXT.md` to `arbiter: disabled` | **BLOCKED** (H-18) — the store the user just created is already protected |
| O6 | Baseline still clean | Repeat scenario G: append a line to `src/hello.txt` | **ALLOWED** — onboarding must not leave the repo over-gated |

### Results — fill in

| # | Step | Codex | Claude | Match? |
|---|------|-------|--------|--------|
| O1 | catalog |  |  |  |
| O2 | dormant doctor |  |  |  |
| O3 | init scaffold |  |  |  |
| O4 | restart banner |  |  |  |
| O5 | H-18 post-init |  |  |  |
| O6 | baseline allow |  |  |  |

O1 failing (missing or unloadable generated skills) is a **surface-generation** finding, not
an enforcement one — capture which entries are missing versus the shipped
`plugins/ca-codex/skills/` set. O3/O4 failing feeds directly into #287.

---

## 6. Out of parity **by design** — do not count these as failures

These are ledgered exceptions (`docs/parity.md`), not regressions:

- **No statusline** on Codex (no statusline surface exists).
- **No Read-tool governed-file notices** — Codex has no read tool (reads go via shell), so the
  H-12-style "this file is governed by ADR-NNNN" notice on Read cannot fire.
- **Transcript pruning engine** is Claude-format only; the audit **staleness-warn** (the
  host-neutral part) still runs on Codex via `UserPromptSubmit`.
- **`prune` and `statusline`** have no Codex surface entry — capability-gated exclusions
  (`has_prunable_transcript` / `has_statusline` are false for the Codex host), rendered out
  of the generated catalog at build time. Their absence in O1 is correct.

> Since M3 the full command/skill surface **is** generated for Codex
> (`plugins/ca-codex/skills/` + `routines/`, `$ca-…` spellings baked in) — a missing command
> that is not in this list is a regression, not a ledgered exception.

## 7. Troubleshooting a "nothing blocks" result

In order of likelihood:

1. **Hooks not trusted** (most common) — approve ca-codex's handler hashes in Codex; re-run.
   `codeArbiter: doctor` should also flag an un-trusted state.
2. **No working interpreter** — the hooks need `python3`/`python` on PATH; a Store-stub python
   fails the gate open. `python3 --version` and `python --version` from the session cwd.
3. **Wrong project root** — if the session cwd is a subdirectory, confirm the repo root is
   resolved (the fixture is a flat repo, so this should not bite; #260 added the toplevel
   climb).
4. **CONTEXT.md not active** — the fixture ships `arbiter: enabled`; if you edited it, the
   guards go dormant. Re-scaffold with a fresh fixture. (In the `--bare` fixture, dormant
   before `$ca-init` is the **expected** starting state, not a failure — O1/O2 run dormant.)

## 8. What a PASS unblocks

Seven-for-seven enforcement parity (§4), six-for-six onboarding parity (§5), plus persona
injection (§3) is the live confirmation the campaign has been waiting on. It clears
`feat/codex-support-m0` to merge to `main` (whose PR should list `Closes #255…#270`) and
gives #287 its answer from observed behavior. Capture the LIVE-PENDING items from the spike
as you go: the trust-review UX, the real exit-2 stderr surfaced to the model, and
`commandWindows` on a Windows install.
