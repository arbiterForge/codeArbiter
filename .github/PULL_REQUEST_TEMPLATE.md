<!-- Thanks for contributing to codeArbiter. Fill this out so review is fast. -->

## What & why

<!-- What does this change do, and why? Link the issue it closes. -->

Closes #

## Type of change

- [ ] `fix`: bug fix
- [ ] `feat`: new behavior
- [ ] `docs`: documentation only
- [ ] `refactor`: no behavior change
- [ ] `chore`: deps, tooling, reverts

## Checklist

- [ ] Branched off `main` (not a direct write to `main`)
- [ ] Conventional Commits used in the commit messages
- [ ] Tests added/updated for behavioral changes (`plugins/ca/hooks/tests/`)
- [ ] Impact-bounded local verification is green under the shared [`verification-boundary`](../core/surface/includes/verification-boundary.md); exhaustive exact-head proof is delegated to required GitHub Actions checks
- [ ] Version bumped if any shipped payload file changed (CI enforces this)
- [ ] `CHANGELOG.md` entry added
- [ ] ADR recorded via `/ca:adr` for any architectural decision
- [ ] New behavior ships off-by-default / `preview` where appropriate
- [ ] Hooks unchanged, or `docs/hooks.md` updated and the no-network invariant preserved

## Notes for the reviewer

<!-- Anything that helps review: tradeoffs, conflict-hierarchy level, follow-ups. -->
