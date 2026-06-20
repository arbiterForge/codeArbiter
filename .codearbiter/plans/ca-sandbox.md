# Plan: ca-sandbox

Source spec: `.codearbiter/specs/ca-sandbox.md` (approved 2026-06-20). Governing decision: ADR-0007
(second sibling plugin, path-scoped CI). Spike findings folded in: deps to `/deps` out-of-tree
(CONFIRM-06), env-token auth offline-default (CONFIRM-07), egress allowlist experimental (CONFIRM-08).

Intent: execute via an **ultracode multi-agent workflow** — tasks are sized and dependency-flagged for
parallel fan-out. Per the user, the release ships **complete** (all tasks), but the MVP slice is still
marked for ordering. Each task's `verification` *maps to* a `tdd` obligation; it does not replace tdd's
own red/green/coverage gates.

Pre-flight gap (surfaced, not guessed): `.codearbiter/coding-standards.md` does not exist. Paths follow
the `plugins/ca/` layout + ADR-0007; tooling commands mirror the `plugins/ca/tools` block in
`tech-stack.md`. Docker-gated tests gate behind a `docker info` probe (skip when Docker absent).

## AC ledger (from the spec, verbatim intent)

- **AC-01** — `create <url>` clones into a named volume and starts a container; `docker inspect` shows
  no `"Type":"bind"` mount, no `/var/run/docker.sock` mount, and not `Privileged:true`.
- **AC-02** — the mount-arg builder throws on any bind spec; generated argv contains only
  `type=volume`/`type=tmpfs`.
- **AC-03** — a process inside the box cannot read a host-planted canary at its real abspath; a
  negative control proves the canary is host-readable.
- **AC-04** — first `create` runs nixpacks and tags `ca-sbx:<repo>-<dephash>`; a second `create` from
  the unchanged repo performs no build (cache hit, identical tag).
- **AC-05** — editing a dep manifest/lockfile changes the dephash → rebuild; editing only source → no rebuild.
- **AC-06** — with the source volume at `/work/repo`, baked deps at `/deps` resolve at runtime AND an
  in-place source edit in the volume takes effect on re-run (deps survive + live-editable).
- **AC-07** — nixpacks builds a runnable image for each fixture repo (node/python/go/rust); dephash is
  deterministic (hash twice → identical).
- **AC-08** — offline: `curl github.com` inside fails. clone-then-cut: deps fetched at build, post-run
  egress fails. allowlist (experimental): `curl github.com` succeeds, `curl example.com` fails.
- **AC-09** — `exec <id> -- sh -c 'exit 7'` → JSON `exitCode:7`, stdout/stderr separate, `truncated`
  trips past the byte cap; `execInSandbox()` works from a vitest.
- **AC-10** — `cp <id>:/work/<f> ./out` copies to host; any host→container bind is impossible.
- **AC-11** — `create → exec → cp → destroy` leaves zero `ca.sandbox=1`-labeled containers/volumes
  (cached images excepted); `--keep-volume` leaves the volume; `prune` reclaims a leaked labeled object.
- **AC-12** — (Claude-inside) with env-injected `CLAUDE_CODE_OAUTH_TOKEN` and egress limited to
  Anthropic domains, `claude -p "echo"` succeeds inside the box (dummy token → real `401`) and persists
  across `restart` via the named-volume HOME; `--with-claude` defaults to offline/Anthropic-only.

Governance obligations (ADR-0007 packaging, not behavioral ACs — surfaced per writing-plans as
necessary enablers, not scope creep): **GOV-A** marketplace entry + CONTEXT/marketplace description;
**GOV-B** path-scoped CI; **GOV-C** prose surfaces (skills/commands/INDEX/COMMANDS) wired and ref-clean.

## Task table

Status legend: PENDING → ACCEPTED (flipped by the executor on acceptance). All start PENDING.
Verification commands run in `plugins/ca-sandbox/tools/` unless noted; `[docker]` = gated behind `docker info`.

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|----|---------|--------------|--------------------------|--------|------------|--------|
| T-01 | `plugins/ca-sandbox/tools/{package.json,tsconfig.json,vitest.config.ts}` | `npm install && npm run typecheck` exits 0 (mirrors tech-stack `plugins/ca/tools`) | toolchain compiles | AC-02 (enabler) | — | PENDING |
| T-02 | `plugins/ca-sandbox/.claude-plugin/plugin.json` | `node -e "JSON.parse(fs.readFileSync('plugins/ca-sandbox/.claude-plugin/plugin.json'))"` ok | manifest parses | GOV-A (enabler) | — | PENDING |
| T-03 | `plugins/ca-sandbox/tools/mounts.ts` (+ test) | `npm test mounts` — builder throws on a bind spec; argv contains only `type=volume`/`type=tmpfs` | mount builder rejects all binds | AC-02 | T-01 | PENDING |
| T-04 | `plugins/ca-sandbox/tools/dephash.ts` (+ test) | `npm test dephash` — identical manifest set → identical hash; manifest/lockfile change → different hash | dephash deterministic + manifest-sensitive | AC-04, AC-05 | T-01 | PENDING |
| T-05 | `plugins/ca-sandbox/tools/build.ts` (+ test) | `[docker] npm test build` — first build tags `ca-sbx:<repo>-<dephash>`; unchanged rerun → no build; manifest change → rebuild; nixpacks deps relocated to `/deps` | nixpacks wrap + dephash cache + /deps relocation | AC-04, AC-05 | T-04 | PENDING |
| T-06 | `plugins/ca-sandbox/tools/run.ts` (+ test) | `[docker] npm test run` — `docker inspect` shows no bind, no `/var/run/docker.sock`, not `Privileged`; cap-drop ALL, non-root, read-only root present | isolation flags applied; binds forbidden | AC-01 | T-03, T-05 | PENDING |
| T-07 | `plugins/ca-sandbox/tools/run.ts`, `tools/__fixtures__/node`, `tools/__fixtures__/py` (+ test) | `[docker] npm test layering` — deps at `/deps` resolve at runtime; edit source in volume at `/work/repo`, re-run → edit takes effect; deps still resolve | /deps survives mount + live-editable source | AC-06 | T-05, T-06 | PENDING |
| T-08 | `plugins/ca-sandbox/tools/__tests__/isolation.test.ts` | `[docker] npm test isolation` — in-box read of host canary fails; negative control proves canary host-readable | host-FS isolation behavioral | AC-03 | T-06 | PENDING |
| T-09 | `plugins/ca-sandbox/tools/{create.ts,destroy.ts,registry.ts}` (+ test) | `[docker] npm test lifecycle` — create clones into named volume + starts container; create→destroy leaves zero `ca.sandbox=1` objects; `--keep-volume` keeps; `prune` reclaims a leaked labeled object (label-only state) | create/destroy + label registry | AC-01, AC-11 | T-06 | PENDING |
| T-10 | `plugins/ca-sandbox/tools/network.ts` (+ test) | `[docker] npm test network` — offline: curl fails; clone-then-cut: post-run egress fails; allowlist (experimental): github ok, example fails | network-policy flags | AC-08 | T-06 | PENDING |
| T-11 | `plugins/ca-sandbox/tools/exec.ts` (+ test) | `[docker] npm test exec` — `exec -- sh -c 'exit 7'` → JSON `exitCode:7`, stdout/stderr separate, `truncated` past byte cap; `execInSandbox()` callable from vitest | exec seam JSON contract + export | AC-09 | T-06 | PENDING |
| T-12 | `plugins/ca-sandbox/tools/cp.ts` (+ test) | `[docker] npm test cp` — `cp <id>:/work/<f> ./out` copies to host; host→container bind rejected by the mount builder | host-initiated cp out; reverse-bind impossible | AC-10 | T-06, T-03 | PENDING |
| T-13 | `plugins/ca-sandbox/tools/__fixtures__/{node,py,go,rust}` (+ test) | `[docker] npm test multistack` — each fixture builds a runnable image; dephash deterministic across two builds | multi-stack nixpacks build + deterministic hash | AC-07 | T-05 | PENDING |
| T-14 | `plugins/ca-sandbox/tools/claude-inside.ts`, `skills/sandbox-claude-inside/SKILL.md` (+ test) | `[docker] npm test claude-inside` (DUMMY token) — `claude -p` reaches auth (dummy → `401`), state persists across restart via named-volume HOME, `--with-claude` defaults offline/Anthropic-only | claude-inside env-token + persistence + offline default | AC-12 | T-06, T-10 | PENDING |
| T-15 | `plugins/ca-sandbox/tools/cli.ts` (subcommand wiring: create/shell/exec/cp/destroy) (+ test) | `npm test cli` — each subcommand parses args and dispatches to its module; unknown flag errors | CLI dispatch surface | AC-01, AC-09, AC-10, AC-11 | T-09, T-11, T-12 | PENDING |
| T-16 | `plugins/ca-sandbox/tools/sandbox.js` (built artifact) | `npm run build` then `git diff --quiet -- plugins/ca-sandbox/tools/sandbox.js` (stale build blocks, mirrors farm.js rule) | shipped build is fresh | GOV-B (enabler) | T-15, T-14 | PENDING |
| T-17 | `plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md`, `skills/INDEX.md`, `commands/{sandbox,sandbox-shell,sandbox-exec,sandbox-cp,sandbox-destroy}.md`, `COMMANDS.md` | ca-sandbox-scoped `check-plugin-refs.py` passes; each skill has gated phases + Hard rules; each command has Routes-to/Hard-gate | prose surfaces ref-clean, v2 house style | GOV-C | T-02 | PENDING |
| T-18 | `.claude-plugin/marketplace.json`, `.codearbiter/CONTEXT.md` | marketplace.json parses and contains `{name:"ca-sandbox",source:"./plugins/ca-sandbox"}`; CONTEXT/marketplace descriptions state the two-plugin shape (ADR-0007) | marketplace + identity updated | GOV-A | T-02 | PENDING |
| T-19 | `.github/workflows/ci.yml`, `.github/scripts/check-plugin-refs.py` | path-scoped: a sandbox-only diff skips every `ca` job and runs the docker-gated ca-sandbox tools job; `check-plugin-refs` validates ca-sandbox; per-plugin version-bump guard | path-scoped CI per ADR-0007 | GOV-B | T-16, T-17, T-18 | PENDING |

## Order, dependencies & MVP slice

Dependency layers (each runs after the prior; within a layer, parallelizable):

- **Layer 0 (foundation, parallel):** T-01, T-02.
- **Layer 1 (pure units, parallel):** T-03, T-04.
- **Layer 2 (build):** T-05 (after T-04).
- **Layer 3 (run + lifecycle fan-out, parallel after T-06):** T-06 (after T-03, T-05), then T-07, T-08, T-09, T-10, T-11, T-12, T-13.
- **Layer 4 (claude-inside):** T-14 (after T-06, T-10).
- **Layer 5 (surfaces):** T-15 (after T-09/T-11/T-12), T-17 (after T-02), T-18 (after T-02) — parallel.
- **Layer 6 (build artifact + CI):** T-16 (after T-15, T-14), then T-19 (after T-16, T-17, T-18).

No cycles.

**MVP slice (core "pull an untrusted repo into an isolated, cached box and explore safely"):**
T-01 → T-02 → T-03 → T-04 → T-05 → T-06 → T-07 → T-08 → T-09 → T-12 → T-17 → T-18.
Covers AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-10, AC-11 + GOV-A/GOV-C — a usable, isolated,
dep-cached sandbox with safe file extraction. **Incremental beyond MVP:** T-10 (AC-08 network policy),
T-11/T-15 (AC-09 exec seam), T-13 (AC-07 multi-stack), T-14 (AC-12 Claude-inside), T-16/T-19 (build +
CI). Per the user's "MVP = complete" directive the release bundles all 19, but the slice marks the
shippable core for execution ordering.

## Coverage proof (bijective)

- Every AC covered: AC-01→T-06,T-09 · AC-02→T-03 · AC-03→T-08 · AC-04→T-04,T-05 · AC-05→T-04,T-05 ·
  AC-06→T-07 · AC-07→T-13 · AC-08→T-10 · AC-09→T-11 · AC-10→T-12 · AC-11→T-09 · AC-12→T-14. ✓
- Every task covers ≥1 AC or a surfaced GOV obligation (T-01/T-02/T-16 enablers; T-17/T-18/T-19 =
  GOV-A/B/C, the ADR-0007 packaging obligations explicitly surfaced above). ✓

## Open / triage

- `[NEEDS-TRIAGE]` nixpacks-as-runtime-dependency detection & user-facing "nixpacks not installed"
  message — belongs in T-05's module but is an environment-UX concern; confirm message UX during build.
- `[NEEDS-TRIAGE]` egress hostname-aware forward proxy (the real v1.x replacement for the experimental
  IP allowlist, per CONFIRM-08) — explicitly out of scope for this plan; future work.
- `[NEEDS-TRIAGE]` farm `item-3` integration (run farm workers inside a ca-sandbox) — seam shaped by
  T-11 but integration deferred per spec.

Handoff: this plan routes to execution (here, an ultracode workflow whose stages each run a task through
`tdd`), never to `tdd` directly.
