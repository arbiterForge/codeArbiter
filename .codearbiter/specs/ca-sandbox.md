# Spec: ca-sandbox — local GitHub-Codespace equivalent

Status: approved (brainstorm 2026-06-20). Build gated on Spikes A–C (see Open questions).

## Problem

You want to pull a GitHub repo you're curious about into an isolated, ephemeral environment — never
onto your local filesystem — explore/run it safely, then tear it down. codeArbiter has no such lane:
`spike` mandates disposal, `using-git-worktrees` folds back and tears down, `dev` is maintainer-only,
`preview`/`doctor` write nothing. None gives a "local Codespace."

Caller: the solo developer, exploring untrusted/third-party code without risking the host.

Out of scope (v1): being a general devcontainer manager; multi-host/remote sandboxes; building the
farm `item-3` integration (only the seam is shaped for it); a hand-built dependency detector
(delegated to nixpacks).

## Scope

- A second marketplace plugin `plugins/ca-sandbox/` (sibling to `ca`), housed in this repo, with
  path-scoped CI so sandbox changes never trigger `ca` checks and vice versa.
- Lifecycle: clone-into-named-volume → build (nixpacks, cached by dep-hash) → run (no host bind) →
  interact (shell / exec seam / Claude-inside) → host-initiated `cp` out → destroy.
- **Image layout (proven by Spike A):** the build installs dependencies to an **out-of-tree path
  `/deps`** (exported via `NODE_PATH`/`PYTHONPATH`, and `GOPATH`/`GOMODCACHE`/`CARGO_HOME` + an
  out-of-tree target for go/rust); the live source named volume mounts **only at `/work/repo`**.
  Mounting the volume *over* the app dir shadows baked deps — it is the one layout that does NOT work.
  nixpacks bakes into the app dir by default, so wiring it needs a post-build relocation to `/deps`
  (or a nixpacks phase override) — one open integration item, non-blocking.
- **Load-bearing invariant:** untrusted code in the box cannot reach the host filesystem. Enforced
  structurally (no bind mounts, no docker socket, never `--privileged`, `--cap-drop ALL`, non-root,
  read-only root). Network is configurable (offline / clone-then-cut / allowlist-experimental).
- Controlled egress is host-initiated only (`sandbox cp <id>:/work/<f> ./dest` via `docker cp`).

## Acceptance criteria

1. `create <url>` clones into a named volume and starts a container; `docker inspect` shows no
   `"Type":"bind"` mount, no `/var/run/docker.sock` mount, and not `Privileged:true`.
2. The mount-arg builder throws on any bind spec; generated argv contains only `type=volume`/`type=tmpfs`.
3. A process inside the box cannot read a host-planted canary at its real abspath; negative control
   proves the canary is host-readable.
4. First `create` runs nixpacks and tags `ca-sbx:<repo>-<dephash>`; a second `create` from the
   unchanged repo performs no build (cache hit, identical tag).
5. Editing a dep manifest/lockfile changes the dephash → rebuild; editing only source → no rebuild.
5a. With the source volume mounted at `/work/repo`, the baked deps at `/deps` resolve at runtime
    **and** an in-place edit to source in the volume takes effect on re-run (deps survive + live-editable).
6. nixpacks builds a runnable image for each fixture repo (node/python/go/rust); dephash is
   deterministic (hash twice → identical).
7. offline: `curl github.com` inside fails. clone-then-cut: deps fetched at build, post-run egress
   fails. allowlist: `curl github.com` succeeds, `curl example.com` fails.
8. `exec <id> -- sh -c 'exit 7'` → JSON `exitCode:7`, stdout/stderr separate, `truncated` trips past
   the byte cap; `execInSandbox()` works from a vitest.
9. `cp <id>:/work/<f> ./out` copies to host; any host→container bind is impossible.
10. `create → exec → cp → destroy` leaves zero `ca.sandbox=1`-labeled containers/volumes (cached
    images excepted); `--keep-volume` leaves the volume; `prune` reclaims a leaked labeled object.
11. (Claude-inside, gated on Spike B) with env-injected `CLAUDE_CODE_OAUTH_TOKEN` and egress limited
    to Anthropic domains, `claude -p "echo"` succeeds inside the box and persists across `restart`.

## Open questions — resolved by the spikes (2026-06-20)

- CONFIRM-06 (Spike A) — **RESOLVED.** Deps to `/deps` out-of-tree + `NODE_PATH`/`PYTHONPATH`, source
  volume only at `/work/repo`. Forced the image-layout change above. See
  `.codearbiter/spikes/ca-sandbox-layering.md`.
- CONFIRM-07 (Spike B) — **RESOLVED (caveat).** Env-injected `CLAUDE_CODE_OAUTH_TOKEN` authenticates
  with no host bind; named-volume HOME persists. Hard default: `--with-claude` offline/Anthropic-only,
  never co-mount the token volume with untrusted code. See `.codearbiter/spikes/ca-sandbox-claude-auth.md`.
- CONFIRM-08 (Spike C) — **RESOLVED (caveat).** iptables egress allowlist works but is brittle (CDN
  drift, multi-host, DNS-exfil hole) → ship **experimental**; offline + clone-then-cut are the solid
  defaults; hostname-aware forward proxy is the v1.x fix. See `.codearbiter/spikes/ca-sandbox-egress.md`.

Remaining non-blocking integration item: nixpacks post-build relocation of deps to `/deps`.

Full design, build order, and risks: `~/.claude/plans/i-want-to-theory-soft-corbato.md`.
