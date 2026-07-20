# Claude Code / Codex CLI / Pi parity ledger

codeArbiter has three governance hosts generated from one canonical core. The
`ca`, `ca-codex`, and `ca-pi` adapters share `core/pysrc/` and `core/surface/`;
`tools/sync-core.py --check` and `tools/build-surface.py --check` are the drift
gates. `ca-sandbox` is the fourth sibling plugin, but it is infrastructure, not
a governance host.

Final Pi promotion evidence is available as a [sanitized report](./reports/pi-support/promotion.md)
and [machine-readable envelope](./reports/pi-support/promotion.json). Local checks and the hosted
Windows/macOS/Linux matrix for Pi 0.80.5/0.80.10 are green on commit `11df92890722`; scoped CodeQL and
the repository aggregate gate are green on that same commit.

Codex 0.144.1 live verification on 2026-07-11 covered trusted startup and the
H-03 structured block. Pi's implementation and local supported-version
contracts target Pi 0.80.5 and Pi 0.80.10. The completed hosted
Windows/macOS/Linux promotion report records x64 Windows/Linux and arm64 macOS evidence without
presenting the deliberately nonblocking unsupported-latest canary as supported.

## Generated surface

| Surface | Claude Code (`ca`) | Codex CLI (`ca-codex`) | Pi (`ca-pi`) | Evidence |
|---|---|---|---|---|
| Public entries | 39 `/ca:*` commands | 37 `$ca-*` entry skills | 38 `/ca-*` aliases with `/skill:ca-*` fallback | `plugins/*/COMMANDS.md`, `plugins/ca-pi/SKILLS.md` |
| Orchestrator routines | 22 generated skills | 22 generated routines | 22 generated routines | `python tools/build-surface.py --check` |
| Role charters | 28 plugin agents | inline until Codex agent packaging lands | 28 generated roles used by hardened child dispatch | `core/surface/agents/`, `plugins/ca-pi/generated/roles.json` |
| Shared Python | stdlib-only core | byte-identical vendored core | byte-identical vendored core behind bounded bridge | `python tools/sync-core.py --check` |
| Project store | `.codearbiter/` | same store | same store with `HOST: pi` attribution | `.github/scripts/test_pi_shared_store.py` |

Catalog counts are derived from generated outputs: `ca: 39`, `ca-codex: 37`,
and `ca-pi: 38`.

## Enforcement and lifecycle

| Capability | Claude Code | Codex CLI | Pi |
|---|---|---|---|
| Dormant global install | `arbiter: enabled` gates startup | same shared core | enabled marker plus affirmative Pi project trust |
| Startup persona/state | `SessionStart` hook | trusted `SessionStart` hook | `session_start` extension event through the shared bridge |
| EXEC enforcement | `PreToolUse` Bash/PowerShell | exec hook over Codex shell | final wrapper around built-in `bash`; unknown tools fail closed |
| WRITE/EDIT enforcement | Write and Edit hooks | `apply_patch` decomposed per file; opaque blocks | final wrappers around built-in `write` and `edit` arguments |
| READ notices | native Read hook | host-impossible; post-write notices remain | built-in `read` wrapper and shared notice policy |
| Git backstop | shared `.git/hooks` installer | same | same through Pi bridge |
| Status | complete Claude statusline | startup state only | rich footer globally; governance row only when enabled and affirmatively trusted; rate windows omitted |
| Prune/compaction | shared policy plus Claude transcript codec | transcript engine unavailable; audit warning remains | shared policy plus Pi native compaction; no active-session rewrite |
| Role dispatch | Claude subagents | inline review/author fallback | fresh Pi RPC children: single, chain, parallel |
| Process cleanup | host-managed subagents | host-managed inline work | bounded cancellation/timeout plus verified whole-tree cleanup; unhealthy latch on failure |
| Doctor | interpreter, payload, hooks, live H-03 probe | trusted hook/origin diagnostics | package/origin/trust/collision/core/child/wrapper plus footer/background health |

## Pi live surface classifications

| Capability | Status | Pi behavior | Evidence |
|---|---|---|---|
| Rich footer | SUPPORTED | Installed in every interactive parent repository; the governance row requires enabled plus affirmatively trusted state. | `plugins/ca-pi/tools/src/status.ts` |
| Execute permission asks | SUPPORTED | Classified reads allow silently; governed mutation and external side effects ask once for the current invocation. | `plugins/ca-pi/tools/src/policy.ts` |
| Read-only plan mode | SUPPORTED | Plan mode is read-only except for the current canonical spec, plan, and plan ledger. | `plugins/ca-pi/tools/src/plan-mode.ts` |
| Session-only background jobs | SUPPORTED | Jobs terminate and verify descendants at shutdown and are never restored from Pi session entries. | `plugins/ca-pi/tools/src/background-jobs.ts` |
| Generated skill catalog | SUPPORTED | The human catalog is `plugins/ca-pi/SKILLS.md`, outside the loader directory. | `core/hosts.json` |
| Cold platform prerequisite | SUPPORTED | Missing Vitest returns `missing_prerequisite` before fixture execution with `npm --prefix plugins/ca-pi/tools ci --ignore-scripts`. | `.github/scripts/test_pi_platform_contract.py` |

Footer, permission UI, plan UI, and background jobs are parent-interactive only.
Rate-window telemetry is omitted because Pi exposes no supported source. An
unverified cleanup makes the background manager unhealthy, blocks later
launches, and directs the operator to `/ca-doctor`; job state never persists.

Pi doctor reports the canonical active CLI and package origin. Its
module-identity diagnosis proves self-consistency with the operator-launched Pi
runtime; it is not publisher authenticity. Confirm the pinned source with
`pi list`, `pi config`, and the Git tag/commit.

## Distribution and preview features

| Topic | Claude Code | Codex CLI | Pi |
|---|---|---|---|
| Distribution | Claude marketplace | Codex plugin marketplace | pinned Git package `ca-pi-v*`; no npm release |
| Versioning | `ca` SemVer | independent `ca-codex` SemVer | independent nested/root synchronized SemVer |
| `--farm` | Feature Forge `preview`, shared `farm.js` | degraded to the premium path until backend packaging lands | Feature Forge `preview`, parent tool calls the same contained `farm.js` |
| Farm credentials | farm process only | no backend process | farm process only; ordinary children strip `FARM_API_KEY` |
| Embedded worker | not applicable | not shipped | future spike on hardened child runner; not a dependency |

npm packaging is a future spike. A Pi-native embedded farm worker is also a
future spike and must retain the shared plan/result contract; neither changes
the current Git-only install or promotes `--farm` beyond preview.

## Explicit exception ledger

Every exception has a status and a source-visible evidence pointer.

<!-- PI-EXCEPTIONS:START -->
| Surface | Status | Reason | Evidence |
|---|---|---|---|
| Codex native Read event | HOST-IMPOSSIBLE | Codex exposes no equivalent read hook; governed notices still run after writes. | `plugins/ca-codex/includes/codex-host-notes.md` |
| Codex transcript compaction | HOST-IMPOSSIBLE | Claude transcript JSONL is not a Codex session format. | `plugins/ca-codex/includes/codex-host-notes.md` |
| Codex statusline | HOST-IMPOSSIBLE | Codex exposes no plugin statusline surface. | `plugins/ca-codex/includes/codex-host-notes.md` |
| Codex packaged agents | DEGRADED | Roles run inline until a supported packaging surface lands. | `plugins/ca-codex/includes/codex-host-notes.md` |
| Pi rate-window telemetry | HOST-IMPOSSIBLE | Pi exposes no supported provider rate-window source, so the rich footer omits it rather than fabricating data. | `plugins/ca-pi/tools/src/footer-state.ts` |
| Pi active-dispatch doctor self-test | DEGRADED | Public 0.80.5/0.80.10 APIs cannot submit the deterministic wrapper probe through active dispatch. | `plugins/ca-pi/tools/src/doctor.ts` |
| Pi farm route | PREVIEW | Uses the shared backend but awaits real-run promotion under CONFIRM-05. | `plugins/ca-pi/tools/src/farm.ts` |
| Pi npm package | DEGRADED | Git tags are the only distribution path in this release line. | `docs/pi-parity-testing.md` |
<!-- PI-EXCEPTIONS:END -->

## Reproduce the evidence

The deterministic and trusted-live procedure is
[`docs/pi-parity-testing.md`](./pi-parity-testing.md). The final promotion row is
added only after the committed Windows/macOS/Linux by Pi 0.80.5/0.80.10 matrix
and the separately reported nonblocking latest canary complete.
