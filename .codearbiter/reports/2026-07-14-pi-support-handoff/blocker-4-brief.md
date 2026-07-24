# Blocker 4 brief — exact Pi version admission

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Source finding:** handoff HIGH "supported-version split"

## Problem

`plugins/ca-pi/tools/src/compatibility.ts` currently treats Pi `0.80.5` as a minimum and admits every
later semantic-looking version. The approved contract supports exactly `0.80.5` and `0.80.6`.
Unverified `0.80.7`, prereleases, build-decorated or prefix-decorated versions, malformed values, and
`1.x` must not reach any Pi API registration or enabled lifecycle work.

The nonblocking npm-`latest` CI lane currently reports `pi --version` and runs the broad package
test, but does not make installed-runtime admission itself an explicit canary assertion.

## Binding behavior

- Accept only the exact canonical strings `0.80.5` and `0.80.6`.
- Reject older versions, `0.80.7`, later `0.80.x`, prereleases, build metadata, a leading `v`,
  whitespace-decorated values, malformed/partial values, and `1.x` with a fixed diagnosis that names
  the exact supported set and directs the operator to `/ca-doctor`.
- Perform this rejection before any access to the Pi extension API: no handler, command, tool, flag,
  shortcut, status, lifecycle, bridge, audit, or filesystem registration/mutation.
- Preserve prerequisite ordering for admitted Pi versions: Node below `22.19.0` and non-Python-3
  inputs still return their existing fixed diagnoses.
- Keep the supported CI matrix exactly Windows/macOS/Linux × Pi `0.80.5`/`0.80.6`.
- Strengthen the separate `continue-on-error` npm-`latest` canary so it explicitly exercises the
  installed runtime version through the same production admission function before API access. If
  npm latest is outside the supported set, the canary must be visibly non-green with the fixed
  unsupported-version diagnosis; it must not silently treat rejection as support.
- No runtime Pi dependency, dependency/lock change, install-script change, or production canary/test
  switch. No network or dependency install during local implementation.
- Regenerate shipped parent bundle deterministically; child bundle must remain byte-identical.

## Required proof

1. Focused RED tests demonstrate that `0.80.7`, prerelease, and `1.x` are currently admitted.
2. Table-driven unit coverage spans both exact supported versions and every rejected shape above.
3. Shipped/package-path coverage invokes `createCodeArbiterPi` for rejected versions through a Pi API
   proxy and proves zero API property access/registration for every rejection.
4. A canary-focused test resolves the actually installed Pi runtime version and exercises production
   admission; the CI latest job invokes that exact test explicitly after printing `pi --version`.
5. Existing package identity/runtime-origin protections, activation, lifecycle enforcement, parity,
   doctor/backstop, hooklib, generation, and deterministic bundle checks stay green.

## Review focus

- Exact-string admission cannot be bypassed by semver decorations or parser prefix matching.
- Version rejection is the first active boundary and has no Pi API side effect.
- Canary semantics remain nonblocking but cannot false-green an unsupported latest release.
- Diagnostics contain no environment values, paths, package contents, or attacker-controlled raw
  version text.
