# Spec — license-consistency CI check

## Problem

A license change (e.g. the v2.6.0 MIT → AGPLv3 relicense, ADR-0009) must update several
independent surfaces, and human review keeps missing some. This session alone found three drift
instances left behind after the relicense: `plugins/ca/.claude-plugin/plugin.json` still declared
`MIT` (fixed in #151), the top-of-README license notice still used the pre-#149 "available
separately" offering wording (fixed in #151), and `plugins/ca-sandbox/.claude-plugin/plugin.json`
still declares `MIT` (open). There is no mechanical guard, so a partial relicense ships silently.

## Caller

The maintainer / release process. "Done" = a dedicated CI check that goes **red** when any project
license-declaration surface disagrees with the canonical license, so a future license change cannot
land on only some surfaces.

## Scope

**In scope — the project's own license-declaration surfaces:**
- `plugins/ca/.claude-plugin/plugin.json` `license` field — the **canonical source of truth** (SPDX).
- `plugins/ca-sandbox/.claude-plugin/plugin.json` `license` field — must equal the canonical.
- `LICENSE` file — its text family must match the canonical SPDX.
- `README.md` version-line license badge.
- `README.md` license-notice callout prose.
- A one-field data fix included in this work: set `ca-sandbox`'s manifest `license` to
  `AGPL-3.0-only` (decided 2026-06-27; the relicense oversight, same class as ca's). ca-sandbox
  0.1.1 is untagged, so this needs no version bump.

**Out of scope:**
- Third-party / transitive dependency licenses (`package-lock.json`, `node_modules`) — never read.
- Historical references to a prior license (CHANGELOG entries, ADR-0009 narrative) — never read; the
  check reads only the enumerated surface files, never a repo-wide grep.
- `marketplace.json` (carries no `license` field today).
- The CLA's legal substance, and the *choice* of license itself — that stays a human/ADR decision.
- Asserting the full LICENSE text verbatim — only the family-identifying header is checked.

## Design

Canonical SPDX is read from `plugins/ca/.claude-plugin/plugin.json`. A small `LICENSE_FAMILIES`
table maps an SPDX id → the markers that identify that license on each surface (LICENSE-file header
substrings, README badge marker, README prose marker). The check is otherwise license-agnostic: a
future relicense changes ca's manifest + adds/uses the family entry, and the check then forces every
other surface to match. Retired commercial-**offering** phrases are a fixed forbidden list (the prose
guard), independent of which license is current.

Implementation mirrors `_releaselib` / `check_badge_consistency.py`: stdlib-only Python, pure
functions over file contents that **never raise on malformed input** (degrade to a reported finding),
plus a CLI entrypoint, with a unit test file. Wired into `.github/workflows/ci.yml` as a dedicated
job in the required-checks aggregation.

For `AGPL-3.0-only` the family markers are: LICENSE header contains `GNU AFFERO GENERAL PUBLIC LICENSE`
and `Version 3`; README badge contains `license-AGPL_v3`; README notice contains `AGPLv3`.

## Acceptance criteria

1. **Manifest agreement.** Given the two plugin manifests' `license` values and the canonical SPDX,
   the check passes iff both equal the canonical; a manifest whose `license` differs (e.g. `MIT`)
   fails with a finding naming the file and both values. (pure fn over inputs)
2. **No stale prior-license string.** A manifest `license` equal to a known prior license (`MIT`)
   fails specifically as a stale-relicense finding, even if both manifests agreed on it — the
   canonical is AGPL-family, so MIT can never pass. (pure fn)
3. **LICENSE-file family match.** Given the LICENSE file text and the canonical SPDX, the check
   passes iff the text contains all family-identifying markers for that SPDX (AGPL-3.0-only →
   `GNU AFFERO GENERAL PUBLIC LICENSE` + `Version 3`); a LICENSE file missing a marker fails. (pure fn)
4. **README badge match.** Given the README text and canonical SPDX, passes iff the family badge
   marker (`license-AGPL_v3`) is present; absent/mismatched badge fails. (pure fn)
5. **README notice names the canonical license.** Given the README text and canonical SPDX, passes
   iff the family prose marker (`AGPLv3`) is present in the notice; a notice naming only a prior
   license fails. (pure fn)
6. **Prose offering-guard.** Given the README text, fails if it contains any retired offering phrase
   in the fixed forbidden set (`available separately`, `offers the same code`); the current
   post-#151 README (which uses `separate proprietary terms` / `not offered at this time`) passes.
   A finding names the offending phrase. (pure fn)
7. **Unknown canonical SPDX is a clear failure, not a crash.** If ca's manifest declares an SPDX with
   no `LICENSE_FAMILIES` entry, the check fails with a "no family mapping" finding (degrade, never
   raise) — so adding a relicense without a family entry is caught, not silently passed. (pure fn)
8. **Never raises on malformed input.** Missing file, unparseable JSON, or non-string input yields a
   reported finding (and non-zero CLI exit), never an exception. (pure fn)
9. **Live repo passes after the ca-sandbox fix.** Run against the real repo with ca-sandbox set to
   `AGPL-3.0-only`, the check exits 0; with ca-sandbox left `MIT`, it exits non-zero naming that file.
   (integration over real files)
10. **CI wiring.** `.github/workflows/ci.yml` defines a license-consistency job that runs the check
    and is included in the required-checks aggregation, so a red check blocks merge. (structural)

## Open questions

None blocking. Both design decisions resolved with the user 2026-06-27: (a) ca-sandbox → AGPL-3.0-only
(fix it; check enforces both manifests); (b) identity + narrow prose guard (AC-6).
