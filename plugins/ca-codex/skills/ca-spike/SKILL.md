---
name: ca-spike
description: Exploratory spike on a throwaway branch — answer a named question with disposable code. Never merges; exits to a findings note or $ca-feature.
argument-hint: "<question to answer> [timebox]"
---

# $ca-spike — exploratory spike

The sanctioned lane for "I need to write code to find out." Spike code is disposable by contract:
it never merges, never PRs, and never becomes the implementation. What survives a spike is the
*answer*, written down — the code is burned.

## Flow

1. **Name the question** — a spike without a falsifiable question is just freelancing. Restate
   `$ARGUMENTS` as the question the spike answers and the timebox (default: one session). STOP for
   the user's confirmation.
2. **Branch** — create `spike/<slug>` from the current branch. All exploratory code and experiments
   stay on it; only the completed findings file may later cross back to the parent.
3. **Explore** — no `tdd`, no plan, no review fleet. Two rules survive even here: no secret leaves
   the approved store, and no irreversible operation (prod data, destructive migration) runs from a
   spike.
4. **Exit — exactly one of:**
   - **Answered** → write the findings to `<project-root>/.codearbiter/spikes/<slug>.md`
     (the question, what was tried, the answer, what it implies), and commit only that findings file
     on `spike/<slug>`. Return to the parent branch and run
     `git restore --source spike/<slug> -- .codearbiter/spikes/<slug>.md` to transfer only the
     committed findings file, review it, and commit that one file through `$ca-commit`; do not
     merge the spike branch. Then delete the spike branch. If the answer warrants building, hand the
     findings to `$ca-feature` — the spike file seeds
     `brainstorming` (`${CLAUDE_PLUGIN_ROOT}/routines/brainstorming/SKILL.md`); the spike code is reference material, never the implementation.
   - **Timebox expired, no answer** → record that in the findings file and use the same findings-only
     transfer before deleting the spike branch.

## Hard gate

MUST NOT merge or PR a `spike/*` branch — its only exits are a findings file and deletion. Do not
transfer spike code: the parent may receive only the committed findings file. MUST NOT copy spike
code into an implementation branch wholesale; implementation re-enters through
`$ca-feature` and `tdd`. Secret-handling and irreversibility rules hold even in a spike. Commits on
a `spike/*` branch are exempt from `commit-gate` — the exemption is safe because no spike commit is
merged and the parent may copy only the committed findings file's contents, never spike code.

## When NOT to use

- You already know what to build → `$ca-feature`.
- Diagnosing a defect → `$ca-debug` (investigation with a structured exit).
- A question answerable by reading code or docs → `$ca-btw`.
