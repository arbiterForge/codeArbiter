# Hackathon PR #313 integration receipt

## Scope

PR #313 absorbs 16 GPT-authored corrective and parity PRs, represented by 29
source commits and 126 unique manifest paths. Dependabot PR #336 remains outside
the submission because it is automated dependency maintenance rather than
hackathon implementation or corrective analysis.

The exact inventory is in `source-prs.json`; machine-readable application
receipts are in `apply-receipts.json`.

## Application result

- Every source commit has an application receipt.
- 123 of 126 manifest paths appear directly in the integrated diff.
- The remaining three paths are the former monolithic `pre-bash.py` copies from
  PR #347. PR #313 had already extracted their H-05 logic into
  `_bashguardlib.py`, so the behavior was ported into the canonical shared core
  and synchronized to Claude Code, Codex, and Pi. This produces four target
  paths and preserves the thin host entry points.
- All other source patches applied directly or were composed with the current
  Pi-era content. No source behavior was silently discarded.

## Conflict decisions

1. H-05 Git checkout/restore protection lives in the extracted shared guard
   core, including separated-value Git global options. The focused guard matrix
   passed 142 assertions after the port.
2. Site generator copy retains both the Pi/Codex host note and the request-flow
   link. The sandbox diagram precedes, rather than replaces, the Pi trust and
   child-process section.
3. Codex documentation reflects current host-provided subagents while keeping
   context creation's stricter isolated-scout requirement.
4. Changelogs retain the Pi unreleased section, the 2.9.1 tribunal fix, and the
   prune-metric correction. The README retains the Pi badge and reports 2.9.1.
5. The docs-mirror board item remains done; the conflicting source hunk was its
   earlier in-progress transition.

## Append-only audit handling

Source audit additions were appended in source-commit order. The five H-05
gate events retain all three identical events emitted at 05:54:34Z.

Commit `09d7818ae2de527b7c4d3d320beaa81ccff81e28` repaired a historical
missing-newline join by rewriting the source branch's final line. Reproducing
that rewrite here would violate H-05. The integrated history instead appends
the intended PR-gate remediation and its correction as two separate records,
followed by a SMARTS decision explaining the normalization. Existing audit
bytes were not removed or rewritten.

## Recovery and preservation

Patch material remains at
`C:/Users/brenn/AppData/Local/Temp/ca-hackathon-apply-74b1c39cf5714703a0cb53ecf50ced05`.
Integration is isolated in
`C:/Users/brenn/projects/codeArbiter-worktrees/integrate-hackathon-pr313`.
The user's primary checkout, untracked plans/spec, gate-event changes, stash,
and existing worktrees have not been modified or cleaned.

## Local verification

- Canonical Python scripts and the 1,057-test hook suite pass.
- The H-05 matrix passes 142 assertions.
- Farm typecheck, 198 tests, build freshness, and critical-level audit pass.
- Pi typecheck/build/tests, all 12 security controls, 18/18 live process-tree
  variants, and the fixtures-only platform aggregate pass.
- The docs site passes typecheck, 418 tests, a 129-page production build, and
  an 18,483-link audit.
- Shared Python, generated host surfaces, host packages, JSON manifests,
  Python compilation, reference graph, secret preview, and diff checks pass.
- The one integration defect found by the site suite was a missing third
  activation-state diagram reference in `enforcement.md`; restoring the source
  PR's figure made the full site lane green.

Candidate commit/CI, Pi evidence rebinding, final CI, and source PR closure
remain governed by T-11 through T-15 of the approved plan.
