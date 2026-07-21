# Blocker 5 brief — native read normalization and model-visible context

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Source finding:** handoff HIGH "read-context parity test is false-green"

## Problem

Pi's native `read` tool supplies `{path: ...}`. `PiHost.normalize_tool_input()` defines the canonical
`{file_path: ...}` shape consumed by shared `pre-read.py`, but `pi-bridge.py` currently forwards the
native input unchanged. A governed native read is therefore silently treated as a miss.

The TypeScript adapter also drops the `context` returned by the pre-read `tool_call`. Its current
read-context test fabricates a `tool_result` bridge response, but the real bridge has no
`tool_result`/READ route. That fake-only path does not prove any context reaches the next model turn.

## Binding behavior

- Normalize Pi native read input through the canonical host seam before invoking shared
  `pre-read.py`: native `path` must reach shared core as `file_path`, without changing the native
  parameters passed to Pi's real read executor.
- Preserve the exact non-empty shared `additionalContext` returned by the pre-read `tool_call` on the
  actual native read result that Pi places in model context.
- Preserve native read result content/details and append at most one bounded, secret-redacted,
  codeArbiter-owned text block using the existing notice identity/de-duplication contract.
- Do not depend on or fabricate a `tool_result`/READ bridge route. If that post-result route is not a
  production route, stop registering/calling it for READ and replace its false-green unit test.
- Governed read: context is visible exactly once to the next model turn. Ungoverned/self/deduplicated
  reads remain native and context-silent. Dormant/bootstrap READ behavior remains native/silent and
  must not call the bridge.
- Read bridge failure remains advisory/fail-open for the read itself, using the existing fixed,
  bounded diagnostic behavior. Mutation enforcement and write/edit post-result notices are unchanged.
- No shared H-rule/workflow reimplementation in TypeScript/Python adapter code. No dependency,
  manifest, lockfile, network, install, production test switch, or host-auth access.
- Regenerate the parent bundle deterministically; child bundle and reviewed lock remain unchanged.

## Required RED/GREEN proof

1. Integrated Python RED: a real native Pi read payload `{path: <governed file>}` through
   `pi-bridge.py` currently returns allow/no context, while canonical `{file_path: ...}` returns the
   shared ADR context. After the fix, native and canonical shapes produce the same exact context.
2. TypeScript RED: the production read wrapper currently returns native content without the bridge's
   `context`; after the fix it preserves native fields/content and appends one owned notice block.
3. Replace the fake `tool_result`/READ test with a negative assertion that no post-result READ bridge
   call is made.
4. Real installed-Pi RPC test with a deterministic local provider must invoke Pi's actual native
   `read` tool against a governed fixture. On the next provider turn, capture the exact `toolResult`
   content Pi exposed to the model. Assert the native file content is unchanged, the exact shared ADR
   context is present once in the owned notice, no context is dropped/duplicated, and no fake event
   seam can make the test green. Run this in the supported-version CI matrix.
5. Add a real ungoverned-read control proving the provider sees only native result content and no
   codeArbiter notice.
6. Full Pi/package/RPC/parity/doctor/hooklib/generation/typecheck and deterministic bundle checks stay
   green.

## Security and review focus

- The adapter must normalize only protocol structure; all governance/context selection remains in
  shared core.
- Model-visible context crosses the existing redaction and byte-boundary before insertion; secrets,
  control bytes, and oversized output cannot bypass it.
- Native result metadata and errors cannot be replaced or converted into success.
- The real-Pi test must capture the actual next-turn `toolResult`, not a fake handler return, UI
  notification, provider prompt, or separately invoked hook output.
