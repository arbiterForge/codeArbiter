# ca-sandbox

A locally-hosted GitHub-Codespace equivalent for codeArbiter (ADR-0007). Pull a repo you're curious
about — including untrusted code — into an **ephemeral, isolated container**, explore or run it safely,
then tear it down. The clone lives on a named volume. Build preparation uses an owned temporary
host copy; cleanup uncertainty is reported separately. The running container has no host filesystem
bind mounts.

This is an **infrastructure** plugin, a sibling to the `ca` governance plugin in the same marketplace.
It is independent of `ca`: CI is path-scoped and versions bump per-plugin.

## Requirements

Docker with a reachable daemon (`docker info`) and Node 20.6+ are required. An already installed nixpacks (host or existing Windows WSL bridge) is preferred. The fallback supports Node/Python dependencies. The reviewed Nixpacks profile selects Node/Python plus Go (`go.mod`) and bounded non-workspace Rust (`Cargo.toml`) explicitly. Go/Rust use the existing digest-pinned build image as their runtime image and retain all source files; every generated external image reference is checked. Fixed Go/Rust manifests and optional config/toolchain files must be owned regular UTF-8 files, at most 1 MiB each, with safe ancestors. Rust `Cargo.toml` containing the literal `workspace` or any backslash is conservatively unsupported, including escaped/complex workspace spellings; this admission check is not a TOML parser. Go command metadata is bounded and checked. These controls do not claim a reproducible Nix/package dependency closure. It refuses project `nixpacks.toml`/`nixpacks.json`, an existing `.nixpacks` output tree or `.ca-sandbox.nixpacks.Dockerfile` before generation, preserving those paths. Custom Nixpacks configurations and other provider stacks are unsupported. Without nixpacks the packaged Dockerfile fallback supports Node/Python dependencies. The driver never installs host tooling. Consumer projects need no maintainer spike notes or ADR files.

## Runtime isolation

The driver starts the box without host bind mounts or a Docker socket. Its runtime controls include:

- No bind mounts (the mount builder rejects any bind spec); the repo lives on a **named volume** at
  `/work/repo`, deps out-of-tree at `/deps`.
- No `/var/run/docker.sock` mount; never `--privileged`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only root, non-root user, resource caps.

Getting work **out** is host-initiated only: `sandbox cp <id>:/work/<file> <hostDest>` (a `docker cp`
pull). The container is never given any path back into the host.

## Commands

Replace `<plugin root>` with the installed ca-sandbox plugin directory. Run the bundled driver with Node:

```
node "<plugin root>/tools/sandbox.js" create <url> [--net offline|clone-then-cut|allowlist]
node "<plugin root>/tools/sandbox.js" shell <id> [--shell sh|bash]
node "<plugin root>/tools/sandbox.js" exec <id> -- <cmd> [args...]
node "<plugin root>/tools/sandbox.js" cp <id>:<containerPath> <hostDest>
node "<plugin root>/tools/sandbox.js" destroy <id> [--keep-volume]
node "<plugin root>/tools/sandbox.js" prune
```

State is label-only: the set of sandboxes IS the set of docker objects labeled `ca.sandbox=1`
(per-instance `ca.sandbox.id=<id>`). There is no JSON state file to drift.

> **Git Bash users:** a bare container path in `exec` (e.g. `exec <id> -- ls /work/repo`) is rewritten
> by MSYS path conversion *before* it reaches the CLI, becoming a Windows path. Wrap the command —
> `exec <id> -- sh -c 'ls /work/repo'` — or set `MSYS_NO_PATHCONV=1`. PowerShell and cmd are unaffected.

## Network policies and staging

Ordinary exploration runtime is **offline** (`--network none`). The accepted request names `clone-then-cut` and `allowlist` also currently resolve to offline; the experimental allowlist helper is not integrated into ordinary create. Results distinguish requested and effective policy. Clone/build helpers still fetch repositories and dependencies. Never expand network access incidentally.

The clone lives on a named volume. Build copies it into a temporary host build-context directory, removes that staging copy after use, and reports uncertain cleanup with its identity. The running sandbox has no host bind or socket; this does not mean source never touches host staging. Shell exit detaches; explicitly destroy the exact sandbox id when finished. Broad `sandbox prune` is separate and targets its container and volume discovery sets, captured at different times.

## Image caching

V2 cache tags are `ca-sbx:v2-<sha256>`, independent of the temporary checkout basename. The key includes manifest/lockfile content, effective builder/version, Docker target platform and build templates/options. Reuse verifies the cache-key label and immutable image ID. Old cache tags remain intact. Dependencies install at `/deps` with `NODE_PATH`/`PYTHONPATH` so the source volume at `/work/repo` does not shadow them.

## Claude inside a separate box

For an explicitly requested Claude-inside session, follow the packaged
[sandbox-claude-inside](skills/sandbox-claude-inside/SKILL.md) instructions.
That routine uses `tools/claude-inside.js` with an environment-injected
`CLAUDE_CODE_OAUTH_TOKEN` and a dedicated home volume. It defaults to offline
and keeps the token volume separate from untrusted repository runs.

## Development

The driver is TypeScript on Node 20, shipped as the built `tools/sandbox.js`.

```
cd tools
npm install
npm run typecheck
npm test          # docker-gated suites run serially (fileParallelism off)
npm run build     # rebuilds sandbox.js; the shipped artifact must be in sync
```

### Docker-required mode

Most of this suite spins real containers. Without a Docker daemon those suites
skip themselves, which is right on a laptop and wrong on CI: a green run that
exercised none of the container behaviour proves nothing about a driver whose
whole job is containing an **untrusted** repository. Two environment variables
make that explicit (issue #406):

| Variable | Effect |
| --- | --- |
| `CA_SANDBOX_REQUIRE_DOCKER=1` | An unavailable daemon **fails** the run instead of skipping. Set by the required CI job. |
| `CA_SANDBOX_DOCKER_SENTINEL=<path>` | Each real-container layer appends its name to `<path>` when it starts. |

CI sets both, then runs
`python .github/scripts/check_sandbox_docker_layers.py --sentinel <path>`, which
fails unless every layer the sources declare actually recorded a run. Locally,
leave both unset for the usual self-skipping behaviour.
