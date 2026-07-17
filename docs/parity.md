# Claude Code / Codex CLI / Pi parity ledger

codeArbiter has three governance hosts generated from one canonical core. The
`ca`, `ca-codex`, and `ca-pi` adapters share `core/pysrc/` and `core/surface/`;
`tools/sync-core.py --check` and `tools/build-surface.py --check` are the drift
gates. `ca-sandbox` is the fourth sibling plugin, but it is infrastructure, not
a governance host.

Final Pi promotion evidence is available as a [sanitized report](./reports/pi-support/promotion.md)
and [machine-readable envelope](./reports/pi-support/promotion.json). Local checks and the hosted
Windows/macOS/Linux matrix for Pi 0.80.5/0.80.6 are green on commit `f457decbf799`; scoped CodeQL and
the repository aggregate gate are green on that same commit.

Codex 0.144.1 live verification on 2026-07-11 covered trusted startup and the
H-03 structured block. Pi's implementation and local supported-version
contracts target Pi 0.80.5 and Pi 0.80.6. The completed hosted
Windows/macOS/Linux promotion report records x64 Windows/Linux and arm64 macOS evidence without
presenting the deliberately nonblocking unsupported-latest canary as supported.

## Generated surface

| Surface | Claude Code (`ca`) | Codex CLI (`ca-codex`) | Pi (`ca-pi`) | Evidence |
|---|---|---|---|---|
| Public entries | 39 `/ca:*` commands | 37 `$ca-*` entry skills | 38 `/ca-*` aliases with `/skill:ca-*` fallback | `plugins/*/COMMANDS.md`, generated skill indexes |
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
| Status | complete Claude statusline | startup state only | extension-owned compact status key, not a footer replacement |
| Prune/compaction | shared policy plus Claude transcript codec | transcript engine unavailable; audit warning remains | shared policy plus Pi native compaction; no active-session rewrite |
| Role dispatch | Claude subagents | inline review/author fallback | fresh Pi RPC children: single, chain, parallel |
| Process cleanup | host-managed subagents | host-managed inline work | bounded cancellation/timeout plus whole-tree cleanup |
| Doctor | interpreter, payload, hooks, live H-03 probe | trusted hook/origin diagnostics | package/origin/trust/collision/core/child/wrapper diagnostics |

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
| Pi complete footer | DEGRADED | Pi exposes extension status, not ownership of the full footer. | `plugins/ca-pi/includes/pi-host-notes.md` |
| Pi active-dispatch doctor self-test | DEGRADED | Public 0.80.5/0.80.6 APIs cannot submit the deterministic wrapper probe through active dispatch. | `plugins/ca-pi/tools/src/doctor.ts` |
| Pi farm route | PREVIEW | Uses the shared backend but awaits real-run promotion under CONFIRM-05. | `plugins/ca-pi/tools/src/farm.ts` |
| Pi npm package | DEGRADED | Git tags are the only distribution path in this release line. | `docs/pi-parity-testing.md` |
<!-- PI-EXCEPTIONS:END -->

## Reproduce the evidence

The deterministic and trusted-live procedure is
[`docs/pi-parity-testing.md`](./pi-parity-testing.md). The final promotion row is
added only after the committed Windows/macOS/Linux by Pi 0.80.5/0.80.6 matrix
and the separately reported nonblocking latest canary complete.
