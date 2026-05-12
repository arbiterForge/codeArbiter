# /add-dep "package-name[@version]"

## Purpose

Vet and add a new third-party dependency. No install command runs before the `dependency-reviewer` agent clears the package. Hard block on denied licenses and supply-chain concerns.

## Usage

```
/add-dep "express@5.0.0"
/add-dep "lodash"          # latest version, reviewer checks it
/add-dep "some-image:tag"  # container base images
```

Specify the exact version if you have one. If no version is specified, the reviewer evaluates the latest available version.

## Routes To

`dependency-reviewer` agent (`${FRAMEWORK_ROOT}/.agents/agents/dependency-reviewer.md`). Agent reads `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md` for allowed licenses, denied licenses, provenance requirements, and CVE policy.

## After approval

After the reviewer clears the package, codeArbiter shows the install command for user confirmation. The lock file change MUST be committed alongside the `package.json` change — never one without the other.

## When NOT to Use

- To remove a dependency: use `/feature` or `/fix` with the change described
- To update an existing dependency: same — changes to `package.json` route to `dependency-reviewer` automatically via `/pr`
- To ask about a package without installing it: use `/btw`
