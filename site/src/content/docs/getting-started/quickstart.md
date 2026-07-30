---
title: Protect Your First Repository
description: "Opt a disposable repository into codeArbiter, verify the live hook path with doctor, and run a first host-native command."
journey:
  level: Foundation
  time: 15 min
  outcome: "a disposable, opted-in repository with a verified SessionStart briefing, real H-03 hook block, and first status report."
  prerequisites:
    - One supported host adapter installed
    - Python 3 on PATH
    - Git identity configured
  proof: "Doctor sees BLOCKED [H-03], and status names the branch, stage, tasks, questions, and overrides."
---

This walkthrough produces a reproducible proof without relying on a fictional application bug or
an agent choosing a particular implementation. You will create a disposable Git repository, opt it
in, restart the host, and let `doctor` exercise a harmless blocking hook.

## Before you start

Complete [Install](/getting-started/install/) for one host. If you have more than one supported
host installed, use [Choose Your Host](/getting-started/choose-your-host/) and review the
[Claude Code and Codex parity boundary](/getting-started/claude-code-and-codex/) before continuing.
Confirm:

```sh
python3 --version || python --version
git config user.email
```

Both commands must print a usable value. The examples below use `ca-first-repo`; delete that
directory when you finish.

## 1. Create a disposable repository

```sh
mkdir ca-first-repo
cd ca-first-repo
git init
printf "# My first protected repository\n" > README.md
mkdir -p src
printf 'print("hello from a real source file")\n' > src/app.py
git add README.md src/app.py
git commit -m "chore: create disposable repository"
```

On PowerShell, create the same fixture with:

```powershell
New-Item -ItemType Directory ca-first-repo
Set-Location ca-first-repo
git init
Set-Content -Encoding utf8 README.md "# My first protected repository"
New-Item -ItemType Directory src
Set-Content -Encoding utf8 src/app.py 'print("hello from a real source file")'
git add README.md src/app.py
git commit -m "chore: create disposable repository"
```

You should have one clean initial commit and a meaningful source file under `src/`. That source file
is load-bearing: context creation intentionally ignores a README-only repository when it decides
between brownfield scouting and greenfield decomposition.

## 2. Opt the repository in

Open the directory in your installed host and invoke the native command:

| Host | Command |
|---|---|
| Claude Code | `/ca:init` |
| Codex | `$ca-init` |
| Pi | `/ca-init` |

For a repository with source, init routes to context creation. Review the generated project context
and complete the activation flow. Before leaving the session, verify
`.codearbiter/CONTEXT.md` begins with a closed frontmatter block containing:

```yaml
---
arbiter: enabled
---
```

Commit the initialized state through the host-native commit command if the context flow has not
already done so.

## 3. Start a fresh session

Close the current host session and open a new one in the same repository. SessionStart should show
the codeArbiter briefing: project stage, blocking questions, in-flight tasks, and the command-catalog
pointer.

If you see no briefing, stop here and use [Troubleshooting](/guides/troubleshooting/). Do not treat
installed files as proof that hooks are active.

## 4. Run the live-fire verification

Invoke doctor:

| Host | Command |
|---|---|
| Claude Code | `/ca:doctor` |
| Codex | `$ca-doctor` |
| Pi | `/ca-doctor` |

Doctor checks the interpreter, installed payload, cache, activation state, and hook wiring. Its
live-fire probe attempts a harmless `git add --all --dry-run`. The pre-tool hook should refuse the
broad add with a message containing:

```text
BLOCKED [H-03]
```

The probe changes no files and stages nothing. That block is the important result: it proves the
host discovered the hook, delivered the tool payload, ran the shared guard, and honored the deny
verdict.

Doctor then reports the probe as healthy. If the shell command runs instead of being blocked, follow
the remediation ladder printed by doctor and the matching symptom in
[Troubleshooting](/guides/troubleshooting/).

## 5. Run your first real command

Ask for the current governed state:

| Host | Command |
|---|---|
| Claude Code | `/ca:status` |
| Codex | `$ca-status` |
| Pi | `/ca-status` |

The report should name the current branch, maturity stage, open tasks, open questions, and overrides
since the last checkpoint. It is read-only.

From here, choose the work in front of you:

- [Build a feature end to end](/guides/feature-lane/)
- [Fix a confirmed defect](/reference/commands/fix/)
- [Run an autonomous sprint](/guides/autonomous-sprints/)
- [Add a dependency safely](/guides/adding-a-dependency/)
- [Record an architecture decision](/guides/recording-adrs/)

## Clean up

When you are done, leave the repository directory and delete `ca-first-repo`. It contains only the
disposable Git history and generated `.codearbiter/` state you just reviewed. Removing it does not
uninstall the plugin from your host.
