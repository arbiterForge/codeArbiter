# Security Policy

## Reporting Vulnerabilities

COVE is a private, internal-use project. If you discover a security vulnerability
in this solution:

1. **Do NOT open a public issue.** Even though Gitea is on a private network,
   treat vulnerability reports as sensitive.
2. **Notify the maintainers directly** via the team's internal communication
   channel (Slack, Teams, or email).
3. **Include:** a description of the vulnerability, the affected repo and
   file(s), steps to reproduce, and potential impact.
4. The maintainers will triage within **2 business days** and communicate
   a remediation plan.

There is no external bug bounty or public disclosure process. COVE repos
are not externally accessible.

## Scanning Tools in Use

| Tool | Purpose | Where It Runs |
|---|---|---|
| **gitleaks** | Scans for secrets, credentials, and API keys | Pre-commit hook (blocking) and CI |
| **Semgrep** | SAST for Node.js/TypeScript security issues | CI (`make sast`) |
| **npm audit** | Scans Node.js dependencies for known vulnerabilities | Pre-commit hook and CI (`make deps-scan`) |
| **PSScriptAnalyzer** | Catches PowerShell security anti-patterns | Pre-commit hook and CI |
| **ansible-lint** | Catches Ansible security anti-patterns | Pre-commit hook and CI |
| **Trivy** | Container image vulnerability scanning | CI (`make container-scan`) |

## Secrets Policy

1. **Zero secrets in repos, ever.** No API keys, passwords, tokens,
   certificates, or private keys committed to any repository.
2. **`.env.example` contains placeholders only.** Never real values.
   The `.env` file itself is in `.gitignore` and is never committed.
3. **Runtime secrets come from AWS Secrets Manager** (primary) or
   **Gitea repo secrets** (CI only).
4. **gitleaks runs on every commit** via pre-commit hook. Blocking at all stages — a detected secret aborts the commit.
5. **If you accidentally commit a secret, rotate it immediately.**
   See the procedure below.

## What to Do If You Accidentally Commit a Secret

**Step 1: Rotate the secret immediately.**
The secret is compromised the moment it is pushed. Rotate it before
anything else.

**Step 2: Do NOT just delete the file and commit.**
Git preserves history. The secret remains visible in the commit log
even after deletion.

**Step 3: Remove the secret from Git history.**

~~~bash
# Option A: BFG Repo-Cleaner (recommended)
echo "THE_SECRET_VALUE" > /tmp/secrets-to-remove.txt
java -jar bfg.jar --replace-text /tmp/secrets-to-remove.txt .
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force --all
git push --force --tags

# Option B: git filter-repo
git filter-repo --replace-text /tmp/secrets-to-remove.txt --force
git push --force --all
~~~

**Step 4: Notify the team.**
Tell maintainers that history was rewritten. Anyone with a local clone
must re-clone or reset to avoid re-introducing the old commits.

**Step 5: Verify the secret is gone.**

~~~bash
git log --all -p | grep "THE_SECRET_VALUE"
gitleaks detect --source . --log-opts="--all"
~~~

Both should return no output.
