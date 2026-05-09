# Dependency Policy

## Rules

- MUST source dependencies only from: PyPI (pinned + hash-checked via Poetry), npm registry (pinned + integrity-checked via package-lock), public container registries mirrored into a private registry [S3+], Gitea internal mirrors. Rationale: SR-3. Verification: `make deps-source-check`.
- MUST run `make sbom` on every build; SBOM stored as release artifact. (SR-4)
- MUST verify license against `ALLOWED_LICENSES.md` before adding any dependency. Verification: `make license-scan`.
- MUST review every new dependency in PR description: name, version, license, transitive count delta (`pipdeptree | wc -l`), maintenance signal (last release date). Rationale: SR-3, SR-11.
- MUST mirror all third-party container base images into private registry [S3+]; build MUST pull only from private mirror. (SR-4)

## Default-Deny Licenses

GPL (any version, except Ansible-core under R-01 exception until [S3]), AGPL,
BSL, SSPL, Commons Clause, custom non-OSI.

## New Dependency Workflow (agent MUST follow)

1. Confirm not already in tree (`pip show <pkg>` / `npm ls <pkg>`).
2. Check license against `ALLOWED_LICENSES.md`.
3. Check most recent release date and last-12-months commit cadence on the upstream repo.
4. Open PR with the four-field justification in description.
5. Hand off to `dependency-reviewer` subagent for sign-off.
6. MUST NOT merge without CODEOWNER review of the dependency line.
