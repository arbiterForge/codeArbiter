# Build Guide — cove-apps-fusion

<!-- PURPOSE: Explain how to set up a development environment and build
     the solution from source. This is for engineers who will modify or
     extend the solution, not just run it.
     Replace all {{PLACEHOLDER}} values. Delete sections that don't apply. -->

## Prerequisites

List everything required before building:

| Requirement | Version | Notes |
|---|---|---|
| Node.js | 22.x LTS | `node --version` |
| npm | >= 10 | bundled with Node.js 22 |
| Ansible | >= 2.15 | `ansible --version` |
| pre-commit | >= 3.6 | `pre-commit --version` (`pipx install pre-commit`) |
| {{Tool}} | {{version}} | {{where to get it}} |

## Clone and Set Up

~~~bash
# Clone the repo
git clone https://gitea.cove.gdit/cove/cove-apps-fusion.git
cd cove-apps-fusion

# Install dependencies and pre-commit hooks
npm install
make install-hooks

# Copy environment variable template
cp .env.example .env
# Edit .env and fill in real values (never commit .env)
~~~

## Install Dependencies

~~~bash
# Node dependencies (installs both backend and frontend workspaces)
npm install

# Ansible collections (if applicable)
ansible-galaxy collection install -r requirements.yml
~~~

## Build Artifacts

~~~bash
# Describe the primary build command(s) here.
# Example for a Python wheel:
#   python -m build --wheel
#
# Example for an Ansible collection:
#   ansible-galaxy collection build
#
# Example for a tarball:
#   tar czf dist/cove-apps-fusion-$(git describe --tags).tar.gz --exclude='.git' .
~~~

## Run Tests

~~~bash
# Backend tests (Vitest + coverage ≥60%)
make backend-test

# Frontend tests (Vitest + coverage ≥60%)
make frontend-test

# Full CI suite (lint + typecheck + tests + security scans)
make ci
~~~

## Verify Pre-Commit Passes

~~~bash
pre-commit run --all-files
~~~

All hooks should pass before opening a PR.

## Known Build Issues

- {{Issue 1 — e.g., "yamllint requires Python 3.11+; earlier versions silently skip it."}}
- {{Issue 2}}


