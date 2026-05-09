# Contributing to cove-apps-fusion

This guide covers how to contribute to this repo. For org-wide standards,
see `cove-templates`.

## Setting Up Locally

~~~bash
# Clone the repo
git clone https://gitea.cove.gdit/cove/cove-apps-fusion.git
cd cove-apps-fusion

# Install pre-commit hooks (requires pre-commit: pipx install pre-commit)
make install-hooks

# Verify hooks pass
pre-commit run --all-files

# Copy and populate environment variables
cp .env.example .env
~~~

## Coding Standards

| Language | Formatter | Linter | Config File |
|---|---|---|---|
| TypeScript/JS | `prettier` (print width 100) | `eslint` + `tsc --noEmit` | `frontend/.prettierrc`, `backend/.prettierrc` |
| PowerShell | (none — manual style) | `PSScriptAnalyzer` | `PSScriptAnalyzerSettings.psd1` |
| Ansible | (none) | `ansible-lint` (moderate profile) | `.ansible-lint` |
| YAML/JSON | `prettier` (via pre-commit) | `check-yaml`, `check-json` | `.pre-commit-config.yaml` |

General rules:
- Inline comments explain **why**, not **what**
- No hardcoded secrets, paths, or environment-specific values — parameterize everything
- Files end with a newline; no trailing whitespace — pre-commit enforces both

## Branch Naming

| Prefix | Use | Example |
|---|---|---|
| `feature/` | New functionality | `feature/add-reboot-handler` |
| `fix/` | Bug fix | `fix/yum-lock-timeout` |
| `hotfix/` | Urgent production fix | `hotfix/cert-renewal` |
| `chore/` | Non-functional (deps, CI, lint) | `chore/update-ansible-lint` |
| `docs/` | Documentation only | `docs/add-rollback-steps` |

All lowercase, hyphens only, no underscores. Delete your branch after merging.

## Pull Request Process

1. Push your feature branch to Gitea.
2. Open a PR against `main`. The PR checklist populates automatically.
3. Fill in the checklist — mark inapplicable items N/A with a note.
4. Request a review. CODEOWNERS will suggest appropriate reviewers.
5. Address feedback with new commits — do not force-push during review.
6. Once approved, merge via the Gitea UI and delete the branch.

## How cove-shared Modules Are Consumed (MVP1)

1. Go to `cove-shared` in Gitea → Releases.
2. Download the release zip for the version you need.
3. Extract the module(s) you need into `src/` or `lib/`.
4. Pin the version in `solution.yaml` under the `dependencies` field.

Do NOT use `git submodule` or `pip install git+https://...`.
