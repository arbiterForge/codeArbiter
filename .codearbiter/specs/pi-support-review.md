# Review — `specs/pi-support.md` (Pi Harness Support, `ca-pi`)

**Reviewer:** Claude (orchestrator), adversarial pass
**Date:** 2026-07-13
**Subject:** `.codearbiter/specs/pi-support.md` @ `feat/pi-support`
**Related:** `.codearbiter/decisions/0013-add-ca-pi-sibling-governance-plugin.md`, `decision-log.md` DECISION-0015
**Verdict:** **Do not implement as written.** Restructure first (§7). The host decision (ADR-0013) is
sound and confirmed by the maintainer; the *spec* is not ready to become a TDD obligation set.

Every claim below is evidenced. External claims cite the upstream source; internal claims cite
`path:line` in this repo. Where I could not verify something, I say so explicitly.

---

## 1. What is correct, and should not be re-litigated

The Pi API claims in the spec are **real**. I verified each load-bearing one against upstream. This is
worth stating plainly because it is the class of claim most likely to be fabricated, and it was not.

| Spec claim | Verified? | Source |
|---|---|---|
| Pi harness exists, installable, extensible | YES | `earendil-works/pi`; npm `@earendil-works/pi-coding-agent` |
| Events `session_start`, `before_agent_start`, `tool_call`, `tool_result`, `session_before_compact`, `session_compact` (`spec:79-86`) | YES — all exist verbatim | `packages/coding-agent/docs/extensions.md` |
| `tool_call` can block a mutating tool and return structure (`spec:71-74`) | YES — documented "Can block"; returns `{ block: true, reason: "..." }` | same |
| `ctx.ui.setStatus("codearbiter", ...)` composable, does not replace the footer (`spec:85`) | YES — independent status keys per extension | same |
| Custom compaction via `session_before_compact` (`spec:83-84`) | YES — handler may return a custom `compaction` result | same |
| Git-backed pinned install (`spec:107-108`) | YES — `pi install git:github.com/user/repo@v1`; refs are pinned tags/commits and `pi update` does not move them | `docs/packages.md` |
| Global install default, project-local supported (`spec:109-110`) | YES — default writes `~/.pi/agent/settings.json`; `-l` writes `.pi/settings.json` | same |
| `/skill:ca-*` native fallback (`spec:87-88`) | YES — skills invoke as `/skill:name` | `docs/skills.md` |

Two upstream facts the spec does **not** mention and should:

- **Extensions load via `jiti`** — TypeScript runs without a build step. Good news; it means the
  generated `ca-pi` extension can ship as `.ts` and still be byte-identity-checked as source.
- **Project trust gates only *project-local* `.pi/extensions`.** Global/user extensions load
  regardless of trust. **2026-07-15 correction:** that load timing does not neutralize trust risk;
  it makes global discovery distinct from adapter authorization. After reading only the canonical
  activation marker, `ca-pi` must require `context.isProjectTrusted?.() === true` before Python/Git
  resolution, bridge/shared startup, enforcement or hook installation, Git reads, or fetch. Missing
  or false trust stays mutation-fail-closed with native untrusted reads and a fixed trust direction.
  Doctor should report both install scope and trust state without a bridge probe or wrapper live fire.

---

## 2. BLOCKER — There is no Pi spike. Codex's campaign made exactly that spike the gate.

This is the finding that reframes the whole document.

**Codex did not ship from a spec.** It shipped from a plan: `.codearbiter/plans/codex-support.md`,
structured M0–M5 (`plans/codex-support.md:66-80`). **M0 was a live spike, and it gated everything**
(`:68-69`) — eight numbered host-API questions answered against the actual Codex Rust source, with
per-claim citations still visible in the code today (`plugins/ca-codex/hooks/_host.py:11-13`:
"source-verified against openai/codex rust-v0.143.0, spike:
`.codearbiter/spikes/codex-extension-surface.md`").

**Several of those answers came back negative and reshaped the design:** Codex has no read tool, no
statusline surface, and plugins cannot ship subagents. Those three discoveries are *why*
`docs/parity.md` has LEDGERED OUT rows at all (`parity.md:24-25, 29, 64`). The spike did not confirm
the plan — it **corrected** it.

**For Pi, the repo contains exactly four references**, all authored 2026-07-13, all governance paperwork:

1. `.codearbiter/specs/pi-support.md` (the spec)
2. `.codearbiter/decisions/0013-add-ca-pi-sibling-governance-plugin.md` (the ADR)
3. `.codearbiter/decisions/decision-log.md:448-469` (DECISION-0015)
4. `.codearbiter/gate-events.log:120-121` (two H-12 REMINDs that fired *while codex was writing the ADR*)

`.codearbiter/spikes/` holds five files — `codex-extension-surface.md` among them — and **nothing for
Pi**. No investigation, no evidence file, no fixture, no issue. ADR-0013's Context (`0013:16-20`)
asserts Pi's capabilities in prose with no citation.

My web verification (§1) happens to confirm most of the API surface, which means codex worked from
real documentation rather than inventing. **But the process skipped the gate that exists to catch the
negative answers, and there are already at least two:**

- **Pi has no built-in subagent API.** Upstream's stated design philosophy: pi "doesn't include
  built-in sub-agents… you can spawn pi instances via tmux, build your own with extensions, or
  install a package that does it your way." The spec's subagent model (`spec:92-96`) — fresh `pi`
  process, isolated context, explicit model, bounded timeout, **cancellation propagation**,
  structured output — is therefore entirely unproven. Cancellation propagation across a spawned
  process is precisely the kind of claim an M0 spike exists to test.
- **The `/ca-*` alias mechanism is unverified.** Pi documents skills as `/skill:name`. Custom `/name`
  slash commands presumably come from pi's `prompts` resource type, but the docs I read do **not**
  confirm that a package-provided prompt registers as a top-level slash command. AC-8 (`spec:140-141`)
  locks a one-to-one `/ca-*` mapping as an obligation on top of an unverified mechanism.

**Required fix:** Add **M0 — live Pi spike** as the gating milestone, in a plan
(`.codearbiter/plans/pi-support.md`), mirroring `plans/codex-support.md`. Nothing downstream is locked
until M0 answers. Question set in §7.3.

---

## 3. BLOCKERS — structural

### B1. The surface generator is structurally binary, and a third host silently corrupts the second

`tools/build-surface.py` bakes host identity into the **template grammar itself**:

```python
# tools/build-surface.py:92
_MARKER = re.compile(r"\{\{(IF:(claude|codex)|ELSE|END)\}\}")
```

Today **every `{{ELSE}}` in the entire template tree means "codex,"** because there are only two hosts.
Introduce a third and every existing `{{ELSE}}` branch silently begins applying to Pi as well. The
failure mode is not "Pi renders wrong" — it is **"the shipped Codex payload changes meaning under
you," silently, across the whole surface.**

On top of the grammar, host names are hardcoded in six enumerations and five branches:

| Site | `build-surface.py` |
|---|---|
| `HOSTS = ("claude", "codex")` | `:54` |
| `PLUGIN_DIR` | `:56-59` |
| `TOKEN_VALUES` | `:61-66` |
| `CMD_FORM = {"claude": "/ca:{name}", "codex": "$ca-{name}"}` | `:68` |
| `CODEX_EXCLUDED_CMDS = frozenset({"statusline", "prune"})`, `CODEX_ONLY` | `:73`, `:76` |
| `MANAGED_SUBTREES` | `:87-90` |
| codex-specific path-rewrite regexes | `:96-97` |
| `if host == "codex"` branches | `:169`, `:179`, `:285-294`, `:311`, `:320` |

`--check` (`:361-380`) is the CI drift gate and it **deletes/flags orphans** in managed subtrees.

`tools/sync-core.py` is milder — a byte-identity copier with a hardcoded plugin list
(`sync-core.py:31-34`, `EXCLUDE = {"_host.py"}` at `:38`) — extending it is genuinely one line.

**The spec treats "generate a third payload" as free (`spec:56-62`, AC-1). It is not, and the risk
lands on Codex, not Pi.** The generator needs an explicit host-set refactor (n-ary `{{IF:host}}`,
`{{ELSE}}` semantics made explicit or removed) as its own task, ideally under `/ca:refactor` with the
existing `--check` proving the ca/ca-codex payloads byte-unchanged.

### B2. The prune "extraction" is a 1,391-line rewrite of the most integrity-sensitive module, with no seam to build on

The spec proposes extracting the pruning engine into "a host-neutral policy plus thin transcript
codecs" (`spec:100-103`). Reality:

- `core/pysrc/_prunelib.py` — **1,391 lines**. `grep hostapi _prunelib.py` returns **nothing**: the
  engine has **zero host abstraction**.
- Nine strategies are coupled to Claude's JSONL byte layout (`s_sidecar_collapse:217`,
  `s_oversize_result_clamp:258`, `s_reasoning_fold:338`, `s_aged_result_condense:367`,
  `s_mcp_payload_condense:394`, `s_shell_tail_keep:430`, `s_superseded_read_condense:483`,
  `s_repeat_reminder_fold:515`, `s_inline_image_evict:553`), on top of
  `Line`/`build_index`/`validate`/`write_in_place`/`self_heal` (`:64, :132, :708, :905, :834`), all
  under a **"never edit bytes, re-serialize only mutated lines"** invariant (`:11-16`).
- The **only** host seam that exists today is a boolean at the entry point:
  `prune-transcript.py:164` → `if not _hooklib.get_host().has_prunable_transcript: return`
  (`hostapi.py:78-83`; set `False` in `ca-codex/hooks/_host.py:179`).

Codex **ledgered the prune engine out entirely** for exactly this reason (`parity.md:27`).

**Required fix:** Cut it. Ledger prune OUT for Pi in v1 using the mechanism this repo already has. If
it is ever wanted, it is its own `/ca:refactor` lane with parity proven by *unmodified* pre-existing
tests — never folded into a host addition.

### B3. Every shared-core edit forces **three** version bumps — and this makes AC-1 mechanically impossible

`sync-core.py` vendors every `core/pysrc/*.py` byte-identically into `plugins/ca/hooks/` **and**
`plugins/ca-codex/hooks/` (`sync-core.py:31-34`), and CI fails on drift (`ci.yml:194`). The
version-bump gates diff `plugins/ca` (`ci.yml:325,336,340,346`) and `plugins/ca-codex`
(`:414,425,429,453`) against their tags. The path filter agrees: `core/**` fans out to `ca:` (`:67`),
`ca-codex:` (`:78`), and `hooks:` (`:83`).

Therefore: **any `core/pysrc/` edit must be re-vendored → that *is* a payload change under both
plugins → both version-bump gates trip.** With `ca-pi`, three.

This collides head-on with **AC-1** (`spec:126-128`), which requires "no drift in the existing Claude
or Codex payloads," while the design promises to extract "newly host-neutral seams" (`spec:36`) and
rewrite prune (`spec:100-103`) — both of which *are* core edits.

**AC-1 is not merely ambiguous; as written it is incompatible with the design.** Pick one:
- (a) AC-1 means "regeneration is clean and idempotent" → **say that**, and add ACs for the `ca` /
  `ca-codex` version bumps and changelog entries a core change forces (AC-29 currently guards
  `ca-pi` only, `spec:186-187`).
- (b) AC-1 means "ca/ca-codex payloads byte-unchanged from `main`" → then the seam extraction and
  prune rewrite are **out of scope by construction**, and the spec must say so.

---

## 4. BLOCKERS — scope, sequencing, and the version floor

### B4. Pi is held to a strictly higher bar than the already-promoted sibling host

The spec demands, on **one branch**, with nothing shipping until all 32 criteria are green
(`spec:17`), everything the Codex campaign deferred or ledgered out across five milestones:

| Capability | Codex — shipped & promoted | `pi-support.md` demands |
|---|---|---|
| Subagents | **M4, still pending.** Plugins cannot ship agents; inline review is the shipped state (`codex-host-notes.md:23-26`, `parity.md:64`) | isolated process subagents (`spec:92-96`), and **AC-18 (`spec:163-164`) says inline "cannot satisfy promotion"** |
| `--farm` | **M5, pending.** Worker files (`plugins/ca/tools/farm.js` 58 KB, `farm.ts` 99 KB) are **not vendored** to `ca-codex`; `--farm` degrades to the premium path (`parity.md:57`, `codex-host-notes.md:33-36`) | ships with shared farm assets and routes through the shared contract (**AC-23**, `spec:173-174`) |
| Prune engine | **LEDGERED OUT entirely** (`parity.md:27`) | ships, *plus* the 1,391-line refactor (B2) |
| Statusline | **LEDGERED OUT** (`parity.md:29`) | ships (**AC-19**, `spec:165-166`) |

And the Codex campaign — the *narrower* one — still has M4/M5 open.

Meanwhile `main` took **135 commits touching ~595 files under `core/`, `plugins/`, `tools/` in the last
30 days**. A single branch carrying 32 acceptance criteria will rot before it lands.

**Required fix:** Milestone it (§7.2). Land each milestone behind the unlisted/beta label as `ca-codex`
did, and ledger the not-yet-shipped surfaces in `docs/parity.md` — the mechanism the spec already puts
in scope (`spec:6`) but then refuses to use.

Note: `docs/parity.md` is **structurally binary** (`| Claude surface | Codex status | Notes |`, four
tables at `:19-31, :35-39, :49-58, :62-67`). Adding Pi means a third column across all four tables, or
a separate ledger. That is a real task; name it.

### B5. The version floor is "today's latest," not a capability minimum

The spec pins **Pi `0.80.6`** and **Node `22.19.0`** (`spec:113`). Verified upstream: those are
*exactly* the current release of `@earendil-works/pi-coding-agent` and the `engines` field of that
release. They are not derived from anything. Node 22.19.0 is not even an independent requirement — pi
raised its own floor there in **0.75.0**.

Contrast the Codex precedent, which justified its floor by capability (`parity.md:5`):
> "minimum rust-v0.143.0, the **source-verified structured-deny baseline**; plugin-bundled hooks came
> on by default earlier, at 0.134.0"

Pinning min-equals-latest excludes every user one release behind for no stated reason.

**Also unstated:** the package **moved scope**. `@mariozechner/pi-coding-agent` (last: 0.73.1,
`engines >=20.6.0`) is **deprecated** — "please use `@earendil-works/pi-coding-agent` instead going
forward." The spec never names the package or repo it is pinning. It must.

**Required fix:** derive the floor from the earliest release exposing the APIs actually used
(`tool_call` block, `setStatus`, `session_compact`, `pi install git:`), state the capability, and name
the package (`@earendil-works/pi-coding-agent`) and repo (`earendil-works/pi`).

### B6. No upper bound and no canary, against a 0.x API with no stability guarantee

Pi ships roughly **10–12 releases per month** and offers **no stated extension-API stability
guarantee**. Breaking changes do land: **0.79.8** removed `@earendil-works/pi-ai/base` and
`pi-agent-core/base` entrypoints; **0.80.0** relocated the legacy global `pi-ai` API to `/compat`;
**0.75.0** raised the Node floor.

ADR-0013 names "Pi extension API changes could invalidate adapter assumptions" as its **top risk**
(`0013:53-54`) and mitigates it with "a documented minimum Pi version" (`0013:57`) — **which protects
against nothing.** A minimum version cannot detect a future breaking change.

**Required fix:** a tested **range** (min + last-verified max), a doctor compatibility probe, and a
**scheduled CI canary against `pi@latest`**, so the third host breaks loudly in CI rather than
silently in a user's session.

---

## 5. Contradictions inside the spec

### C1. Performance gate contradicts the runtime design

- **Design (`spec:67-69`):** "Stateless execution remains the default **unless** a benchmark of 100
  representative events exceeds 100 ms p95 adapter overhead" → exceeding the bar **swaps the execution
  model** (to a persistent bridge/daemon).
- **AC-27 (`spec:182-183`):** the benchmark "reports p95 adapter overhead at or below 100 ms **or
  fails promotion**."

Both cannot be the plan. Worse, the bar is probably unreachable on Windows: cold Python interpreter
start alone is typically 50–90 ms there, before Node spawn overhead, on slow CI runners.

**And it is a bar the shipped hosts have never been held to.** `ca-codex` already spawns **one fresh
Python process per governed event** via `hooks.json`, and `pre-tool-adapter.py:39-45` adds a **second**
subprocess hop (it re-dispatches to `pre-bash.py`/`pre-write.py` via `subprocess.run` purely to
preserve exit-2 across Codex's Windows shell boundary). Pi would be failed for promotion on numbers
`ca` and `ca-codex` ship with today.

**Required fix:** decide which it is. Then set an honest, relative bar — e.g. *"no worse than `ca`'s
existing per-event hook overhead on the same platform"* — and **measure the existing hosts first** to
establish it.

### C2. AC-1 vs. seam extraction — see **B3**.

---

## 6. Gaps

### G1. Subagent recursion is unaddressed — and there is no guard anywhere in the repo to reuse

Global pi extensions load **regardless of project trust**; the spec makes global install the default
(`spec:109`). So a subagent dispatched by spawning a fresh `pi` process **inside an enabled repo** will
itself load `ca-pi`, inject the persona, arm the gates, and be able to spawn its own subagents.

The spec gestures at a "shared concurrency/depth policy" and an over-depth fixture (`spec:94-95`,
AC-17 `spec:160-162`) but **never names the suppression mechanism**. And there is nothing to inherit:

- `ca-codex` **spawns no subagents at all** (`codex-host-notes.md:23-26`).
- A repo-wide grep for `CODEARBITER_SUBAGENT|IS_SUBAGENT|SUBAGENT=` returns **zero hits**. The
  `CODEARBITER_*` vars that exist are `_DEV`, `_BABYSIT`, `_BABYSIT_ONRED`, `_PRUNE*`, `_COMPACT`,
  `_STATUSLINE`, `_WIDTH`.
- Pi documents **no environment variables it sets in child processes**, so `ca-pi` must set and check
  its own.

**Required fix:** name the guard (e.g. `CODEARBITER_SUBAGENT=1` → adapter no-ops on `session_start` /
`tool_call`), and make **AC-17 assert the child does not re-arm governance**. Beware the known
env-var propagation caveats on the hook path.

### G2. No security gate on the adapter, in a repo where a security finding already blocks merges

The adapter spawns subprocesses (`python`, and `pi` for subagents) with **tool-derived input**. The
farm shell-injection-from-env finding is an accepted won't-fix that **re-raises on refactor/bundle
rebuild and blocks merge under `enforce_admins`**. A brand-new spawning surface is very likely to trip
it. (Correction to an earlier statement of mine: there is **no CodeQL workflow file** —
`.github/workflows/` contains only `ci.yml`, `docs.yml`, `release.yml`. CodeQL runs via GitHub's
**default setup**, which scans without path filters. The merge-blocking risk stands; only its
configuration location differs.)

Separately, the bridge passes **raw tool payloads** — bash commands, file contents, which can carry
secrets — into a subprocess and into host-attributed audit lines. **Nothing in the 32 criteria covers
redaction** (cf. the accepted `preview.py` clear-text-logging false positive, redacted upstream).

**Required fix:** a `/ca:threat-model` pass before implementation; an AC for bridge/audit-line
redaction; an explicit expectation for the CodeQL result on the new spawn sites.

### G3. There is no root `package.json` — and pi's manifest **is** `package.json`

Verified: the repo root has **no `package.json`** (`site/` owns its own). Verified upstream: pi reads
the `pi` key from `package.json`; **there is no separate manifest format** ("No separate
repository-root manifest exists — pi reads the `pi` key within `package.json`").

So the spec's "A repository-root Pi manifest" (`spec:108`) quietly means **creating a root
`package.json` in a repo that deliberately has none**, declaring
`{"pi": {"extensions": ["./plugins/ca-pi/extensions"], "skills": [...]}}`. That changes root-level
tooling detection (Dependabot, CodeQL JS scanning, npm). AC-4 (`spec:132-133`) tests it but the spec
never *says* it.

**Required fix:** state it as an explicit, approved consequence — or confirm in M0 whether `pi install
git:` can target a subdirectory package instead.

### G4. `ca-pi` introduces TypeScript to a repo whose governance plugins contain none

`plugins/ca-codex/` is **pure Python + markdown** — its only two non-`.md`/non-`.py` files are
`.codex-plugin/plugin.json` and `hooks/hooks.json`. It has exactly **two** handwritten Python files
(`hooks/_host.py`, 289 lines; `hooks/pre-tool-adapter.py`); the other 42 are byte-identical vendored
core. The only TypeScript in the repo is `plugins/ca/tools/farm.ts` — Claude-only, not vendored to any
sibling.

`ci.yml` is Python-centric: `changes`, `tools`, `ca-sandbox-tools`, `hooks`, `version-bump{,-sandbox,-codex}`,
`prose{,-sandbox,-codex}`, `badge-consistency`, `manifests`, `license-consistency`, `surface`,
`ci-passed`. **There is no TypeScript typecheck or test job for a plugin.** AC-28 (`spec:184-185`)
says "one matrix workflow" as though this is free.

**Required fix:** name the TS toolchain (test runner, typecheck), how Node 22 is provisioned, and how
`pi` itself is installed in CI for the contract and live-fire suites.

### G5. CI/release surface the spec does not enumerate

Concretely, `ca-pi` requires:

| Job | `ci.yml` | Need |
|---|---|---|
| `changes` | `:42-88` | new `ca-pi:` path filter (`core/**` already fans to `ca`/`ca-codex`/`hooks`) |
| `hooks` (**already 3-OS matrix**, `:180-182`) | `:166-313` | host `sync-core --check` (`:194`), `build-surface` tests (`:212`), a `test_pi_adapter.py`, dual/tri-host store test (`:229`), cold-install matrix (`:214`) |
| `version-bump-pi` | twin of `:405-457` | tag namespace `ca-pi-v*` |
| `prose-pi` | twin of `:573` | `check-plugin-refs.py ca-pi` |
| `manifests` | `:502-532` | a `validate_pi_plugin.py` analogue (cf. `validate_codex_plugin.py`, `:530`) |
| `surface` | `:551-571` | repo-wide, always-on; must learn the third host |
| `ci-passed` | `:586-604` | aggregator `needs:` must list every new job |
| `release-pi` | `release.yml`, twin of `release-codex` (`:131`, tag `ca-codex-v*` `:160`) | new |

Good news: the 3-OS matrix the spec wants (AC-28) **already exists** on the `hooks` job. Every other
job is `ubuntu-latest` only.

---

## 7. Required restructure

### 7.1 The spec is the wrong shape and 1.4× too big

House pattern (`specs/context-drift-provenance.md:3`, `specs/metrics.md:3`, `specs/task-writer-harvest.md:3`):

```
**Slug:** <slug> · **Lane:** full · **Status:** approved <date> by <email>
## Problem / ## Scope / ## Acceptance criteria / ## Open questions
```

- `pi-support.md:3-6` uses a nonstandard header (`Status: Pending user approval / Date / Branch /
  Governs`) — **no Slug, no Lane**.
- AC counts across all prior specs run **12–23** (`farm-pluggable-backend` 16, `task-writer-harvest`
  12, `context-drift-provenance` 23). This spec has **32** (`spec:126-195`).
- **Milestones live in plans, not specs.** So the fix is *not* "add milestones to this spec" — it is:
  trim the spec to the house shape and to **one milestone's** worth of scope, and put the sequencing
  in `.codearbiter/plans/pi-support.md`.

### 7.2 Proposed milestones (mirror `plans/codex-support.md`)

| M | Scope | Exit |
|---|---|---|
| **M0** | **Live Pi spike** (§7.3). Gates everything. | `.codearbiter/spikes/pi-extension-surface.md` with per-claim citations, like the Codex spike. Design is **rewritten** from its answers. |
| **M1** | Generator n-ary host refactor (B1) + `sync-core` third target + `plugins/ca-pi/` scaffold + package/manifest discovery + dormancy/activation. | ca/ca-codex payloads byte-unchanged (`build-surface --check`); Pi package discovered; dormant without `arbiter: enabled`. |
| **M2** | Event bridge: `tool_call` canonical mapping + structured blocking + fail-closed on opaque mutation + `tool_result` nudges + git backstop. | Verdict-parity contract suite green; live-fire block probe. |
| **M3** | Command/skill surface (`/ca-*` + `/skill:ca-*`), doctor, status line. | Catalog parity test; doctor suite. |
| **M4** | Subagents (isolated process runner + **recursion guard**, G1). Until then: inline, ledgered DEGRADED — *exactly as Codex ships today*. | Runner suite; child does not re-arm governance. |
| **M5** | Distribution, release-pi, `--farm` packaging decision, parity-ledger completion. | Live promotion evidence (Windows interactive + Linux non-interactive). |

**Ledger OUT for v1** (in `docs/parity.md`, third column): **prune engine** (B2), and `--farm` until
CONFIRM-05 resolves.

### 7.3 M0 spike questions (the Codex spike had eight; these are yours)

1. **Subagents.** Can a spawned `pi` child be driven headlessly with an explicit model, isolated
   context, bounded timeout, **cancellation propagation**, and structured output? Via process spawn,
   RPC mode, or the SDK — which, and at what cost? *(Upstream says pi has no built-in subagents.)*
2. **Recursion.** Does a `pi` child spawned inside an enabled repo load global extensions? Confirm the
   env-var suppression path end-to-end (G1).
3. **Slash commands.** Does a package-provided `prompt` register as a top-level `/ca-*` command, or is
   `/skill:ca-*` the only surface? *(Unverified; AC-8 depends on it.)*
4. **Capability floor.** Earliest pi release exposing `tool_call` blocking, `ctx.ui.setStatus`,
   `session_compact`, and `pi install git:` — the real minimum (B5).
5. **Packaging.** Can `pi install git:` target a **subdirectory** package, or is a **root
   `package.json`** mandatory (G3)?
6. **Trust.** Exact behavior of `project_trust` for global vs. project-local installs; what the user
   sees; what doctor must report.
7. **Block fidelity.** What does the user actually see when `tool_call` returns `{block, reason}` — is
   the reason surfaced verbatim to the model and the human, like Codex's structured deny?
8. **Bridge overhead.** Measured p95 for a Python-subprocess-per-event bridge on Windows/macOS/Linux —
   **and the same measurement for `ca` today**, to set an honest bar (C1).
9. **Compaction.** Does `session_before_compact` allow a policy-compliant custom result **without**
   rewriting the active session file (AC-21 assumes yes)?

### 7.4 Weak acceptance criteria to fix

- **AC-10** (`spec:144-146`) — "wherever the hosts expose equivalent operations" is an **unbounded
  escape hatch**: the test passes trivially if you declare nothing equivalent. Enumerate the corpus;
  commit the exception list to `docs/parity.md` (that is how Codex's LEDGERED OUT rows work).
- **AC-31** (`spec:191-193`) — live evidence is a human artifact, not a test. Name the evidence path,
  as the Codex campaign did (it recorded the live 0.144.1 pass in `parity.md:11-15`).
- **AC-8** (`spec:140-141`) — blocked on M0 Q3.
- **AC-18** (`spec:163-164`) — "inline cannot satisfy promotion" holds Pi to a bar Codex does not meet.
  Either justify the asymmetry explicitly or align it (M4 + DEGRADED ledger row).
- **AC-27** (`spec:182-183`) — see C1.
- **AC-1 / AC-29** (`spec:126-128`, `:186-187`) — see B3.
- Missing entirely: an AC for **secret redaction** in the bridge and audit lines (G2); an AC that the
  **`ca`/`ca-codex` payloads and versions** stay coherent after any core edit (B3).

---

## 8. Housekeeping

- `CONTEXT.md:51-54` still says *"Hosts are Claude Code and Codex CLI only; further hosts require a new
  ADR."* ADR-0013 exists and is accepted, but **CONTEXT.md is not yet updated**. `decision-log.md:469`
  names this as the follow-up. Hard rule: domain vocabulary may not drift from CONTEXT.md.
- `decision-log.md` ends **without a trailing newline**.
- ADR-0013 and `specs/pi-support.md` are both **untracked**.
- `[NEEDS-TRIAGE]` is used in *Out of scope* (`spec:40-41`, `:50-52`) to mark deferred roadmap items.
  Per the terminology lock it means "an out-of-scope **finding** set aside inline, never acted on in
  place." These are roadmap entries, not findings. Minor, but the markers are load-bearing elsewhere.

---

## 9. Bottom line

The Pi harness is real, the API genuinely fits, and the shared-core instinct is right — **this is a
legitimate thing to build, and ADR-0013 is a sound decision.**

But this spec is a 32-criterion, all-or-nothing, single-branch commitment that **skips the spike that
gated and corrected its own predecessor**, demands from host #3 everything host #2 explicitly deferred
or ledgered out, proposes rewriting the repo's most integrity-sensitive module in passing, and rests a
"no drift" criterion on a generator whose template grammar cannot express a third host without
silently changing what the second one means.

**Do M0 first. Let the spike rewrite the design. Then write a normal-sized spec against a milestoned
plan.**
