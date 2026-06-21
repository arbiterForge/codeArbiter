# Changelog — ca-sandbox

All notable changes to the **ca-sandbox** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-sandbox is the sibling *infrastructure* plugin to `ca`; the two version and release independently (ADR-0007).

---

## [0.1.1] — 2026-06-21 — Dependency bump

Dev-toolchain dependency bump for the sandbox driver (`tools/`). No payload behavior change; consolidates Dependabot #112 and #114 into one synced lockfile.

### Changed
- **`tools/` dev dependencies** — `esbuild` `^0.24.0 → ^0.28.1`, `vitest` `^2.0.0 → ^4.1.9` (transitive `vite` dropped). Regenerated `package-lock.json` so `npm ci` is back in sync.

---

## [0.1.0] — 2026-06-20 — Initial preview

First public release, shipping in the **Feature Forge** as `preview`. A locally-hosted Codespace equivalent: it pulls an untrusted repo into an ephemeral, isolated Docker container with no host-filesystem access and configurable egress, caches dependencies by content hash, then tears the box down. Requires Docker and nixpacks on PATH. Off by default; stays `preview` until real-world runs earn a promotion.

### Added
- **Ephemeral isolated sandbox lifecycle** — `/ca-sandbox:sandbox{,-shell,-exec,-cp,-destroy}` over a labeled (`ca.sandbox=1`) container + named volume. `create → destroy` sweeps to zero; `--keep-volume` retains state; `prune` reclaims leaked labeled objects.
- **Hard host-FS isolation** — no bind mounts (the mount builder rejects all binds; volume/tmpfs only), no `/var/run/docker.sock`, non-root, `--cap-drop ALL`, read-only root. Proven by an in-box canary that can neither read the host abspath nor surface the uuid via a whole-FS grep.
- **Content-hash dependency cache** — `dephash` over the manifest set: identical manifests reuse the image, a manifest/lockfile change rebuilds. Deps are relocated to `/deps` so they survive the `/work/repo` volume mount and source stays live-editable.
- **Multi-stack builds** — nixpacks wrap with a generated-Dockerfile fallback when nixpacks is absent; node / python / go / rust fixtures each build a runnable image deterministically.
- **Configurable network policy** — offline by default, clone-then-cut, and an experimental egress allowlist.
- **exec / cp seams** — `execInSandbox()` JSON contract (exit code, separated stdout/stderr, byte-capped `truncated`); host-initiated `cp` out; the reverse host→container bind is structurally impossible.
- **`--with-claude` (experimental)** — run Claude Code *inside* the box with an env-injected token, state persisted across restarts via a named-volume HOME, offline / Anthropic-only by default.
- **Gated skill + command surface** — `sandbox-lifecycle` and `sandbox-claude-inside` skills; the five `/ca-sandbox:*` commands above.
- **Path-scoped CI** (ADR-0007) — a sandbox-only diff runs the docker-gated tools job and skips every `ca` check; a per-plugin version-bump guard; a `sandbox.js` artifact-freshness gate.

### Notes
- **Preview — not yet blessed.** The automated suite (178 tests, including the docker integration specs) is green, but the plugin has **not been proven in real use**. The `--with-claude` path is verified only against a dummy token (a real `401`), never a live interactive session. Help promote it: explore real repos in the box, run `--with-claude`, and report what you see.
