# Pi supported-window promotion to {0.80.5, 0.84.1}

**Governs:** plugins/ca-pi/tools/src/compatibility.ts, .github/scripts/test_pi_platform_contract.py

**Status:** APPROVED 2026-08-09 by the repository owner

**Origin:** user directive 2026-08-09 ("we need to update for the nearest pi version[, we] are way
behind"); window shape user-chosen the same day: keep the 0.80.5 floor, promote the ceiling to
0.84.1 (latest, published 2026-08-07). Prerequisite for the approved-in-principle sidebar feature,
which must target APIs source-verified in the live window.

## Problem

The supported Pi window is exactly {0.80.5, 0.80.10} — four minor lines behind latest 0.84.1 — so
current Pi installs run ca-pi outside the tested envelope, and the upcoming sidebar feature would
be built against a stale API surface. Done = the declared window is {0.80.5, 0.84.1} on every
surface that states it, with the full platform contract proven live at both versions.

## Approach

Flip the single fail-closed version set (`SUPPORTED_PI_VERSIONS` in `compatibility.ts`) and every
declared-version surface that mirrors it, add the 0.84.1 fixtures, and prove the existing
contracts against the new ceiling — fixing any real drift the proof surfaces. This is the
established promotion mechanism (the pi-promotion workflow and per-version contract runners
already exist); no alternative shape exists. Trade-off accepted: a 4-minor jump risks more drift
than incremental promotion, in exchange for landing on the version users actually install.

## Scope

- Replace ceiling 0.80.10 with 0.84.1 in the compatibility set, contract runners, CI matrices,
  fixtures, and every doc surface that names supported versions.
- Verify (and where drifted, fix) the pinned host contracts at 0.84.1: footer factory, widget,
  session-entry usage shape, dispatch/child RPC protocol under delta-only `message_update`
  (0.84.0 removed the cumulative `message` field, pi#7290), inference-broker header forwarding
  with `string | null` values, and the TypeBox APIs 0.84.x removed.

**Out of scope:** the sidebar feature itself (next spec, against the promoted window); dropping
the 0.80.5 floor; supporting intermediate versions (0.81–0.83 are neither tested nor claimed);
any npm/publishing change; Claude Code or Codex host changes.

## Decided parameters

- Window: exactly {0.80.5, 0.84.1} — user-chosen; the diagnosis string and docs name both.
- Historical prose (CHANGELOG entries, decision log, superseded runbook text) keeps "0.80.10" —
  only living surfaces flip; the no-stale-version check scopes to living docs, code, CI, and
  fixtures.
- The 0.84.1 help fixture is captured from the real `pi --help` of the installed 0.84.1, matching
  the existing `pi-0.80.5-help.txt` convention; the 0.80.10 fixture file is deleted with the
  ceiling (nothing references an unsupported version).
- CI matrices keep the two-version × three-OS shape; the advisory `latest` canary job remains
  advisory and unchanged.
- Local proof runs on Windows (named host); CI owns the three-OS matrix.

## Acceptance criteria

1. `SUPPORTED_PI_VERSIONS` is exactly `{"0.80.5", "0.84.1"}`, the compatibility diagnosis names
   those versions, and the compatibility unit tests pin both (red first against the old set).
2. Every living declared-version surface flips: `test_pi_platform_contract.py`'s accepted
   `--pi-version` values, `ci.yml` adapter-contract matrix, `pi-promotion.yml` and its declared
   `.github/pi-promotion-targets.json`, `tech-stack.md`, README, `docs/parity.md`,
   `docs/pi-parity-testing.md`, and the site host/compatibility pages; a repo-wide check proves
   no living surface still claims 0.80.10 as supported.
3. A `pi-0.84.1-help.txt` fixture exists, captured from the real 0.84.1 CLI; fixture-driven suites
   consume it; the 0.80.10 fixture is removed with no dangling reference.
4. The pinned host contracts hold at 0.84.1, each verified against the installed runtime or its
   published source: footer factory (tui/theme/footerData) and `setFooter(undefined)` restore;
   session-entry usage shape consumed by the footer adapter (aggregate totals AND the per-message
   sparkline series); the dispatch/child RPC protocol under delta-only `message_update` (consume
   `message_end` as authoritative or assemble deltas — never the removed cumulative field);
   inference-broker header forwarding tolerating `string | null` header values; and no use of
   the TypeBox APIs 0.84.x removed. Any changelog-named or proof-surfaced drift is fixed
   test-first, not waived.
5. The platform aggregate passes locally at `--pi-version 0.80.5` AND `--pi-version 0.84.1`
   (Windows, named), each installed fresh with scripts disabled in an isolated home; the CI
   matrix runs both versions across Windows/macOS/Linux; the committed promotion record
   (`docs/reports/pi-support/promotion.json` + `.md`) is regenerated for the new window through
   its own `pi_promotion.py` mechanism and `test_pi_promotion.py` passes.
6. Docs and the parity ledger describe the new window accurately; `test_public_pi_docs.py`,
   `test_pi_package.py`, `test_pi_parity.py`, `test_host_descriptors.py`, and the full repo gate
   pass; ca-pi bumps one minor with a CHANGELOG section (window change is user-visible).

## Open questions

None. The window shape is user-decided; intermediate-version behavior (0.81–0.83 installs get the
fail-closed unsupported diagnosis, same as today's non-window versions) follows the existing
compatibility mechanism unchanged.
