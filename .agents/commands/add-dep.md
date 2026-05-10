# /add-dep "package-name[@version]"

## Purpose

Vet and add a new third-party dependency. No install command runs before the `dependency-reviewer` agent clears the package. Hard block on denied licenses and supply-chain concerns.

## Usage

```
/add-dep "express@5.0.0"
/add-dep "lodash"          # latest version, reviewer checks it
/add-dep "some-image:tag"  # for container base images
```

Specify the exact version if you have one. If no version is specified, the reviewer evaluates the latest available version.

## Routes To

`dependency-reviewer` agent (`.agents/agents/dependency-reviewer.md`).

## What Happens Step by Step

1. codeArbiter reads `projectContext/dependency-policy.md` for: allowed licenses, denied licenses, provenance requirements, source requirements
2. `dependency-reviewer` agent evaluates the package:
   - **License check** — is the license in the allowed list? BLOCK if denied
   - **Provenance check** — is the package from an approved registry/source?
   - **Maintenance signal** — last release date, open issues, maintainer activity (flag if unmaintained per policy)
   - **CVE check** — runs audit command from `projectContext/tech-stack.md`; BLOCK on critical CVE without documented justification
   - **Supply chain posture** — does the package have unusual install scripts, unusual permissions, or a suspicious dependency tree?
3. Findings presented to user
4. If BLOCK findings: STOP — do not proceed until user resolves
5. If PASS: codeArbiter presents the install command; user confirms
6. Install command runs
7. Lock file updated
8. Change staged for `/commit`

## Hard Gates

- MUST NOT run `npm install` (or equivalent) before the reviewer clears the package
- BLOCK on any denied license — no exceptions without an explicit override log entry
- BLOCK on known critical CVE without a documented justification in `projectContext/dependency-policy.md`
- BLOCK if the package is not from an approved source per the policy
- If the reviewer cannot determine the license: treat as BLOCK until license is confirmed

## After Approval

Once the reviewer clears the package:
- The install command is shown to the user for confirmation
- After user confirms, the package is installed and the lock file is updated
- The lock file change MUST be committed alongside the `package.json` change — never commit one without the other

## When NOT to Use

- To remove a dependency: use `/feature` or `/fix` with the relevant change described
- To update an existing dependency: same as above — changes to `package.json` trigger `dependency-reviewer` automatically via `/pr`
- To ask about a package without installing it: use `/btw`
