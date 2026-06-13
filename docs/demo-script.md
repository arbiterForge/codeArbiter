# Demo recording script — codeArbiter in motion

The single highest-impact asset the README is missing is **15 seconds of a gate actually firing**.
This file is the shot list. Record it, drop the result at `docs/demo.gif`, and uncomment the
`<!-- DEMO -->` placeholder near the top of `README.md`.

## Why this exact sequence

It shows the one thing prose can't: a gate **blocking**, the human **resolving**, and the work going
green. That BLOCK → resolve → green beat is the product. Don't demo a happy path with no friction —
the friction is the feature.

## Setup

- A throwaway repo already opted in (`/ca:init` done, `arbiter: enabled`), with a small, real bug
  staged to reproduce. The statusline should be wired (`/ca:statusline`) so the arbiter row shows.
- Terminal at ~110×30, a dark theme that matches the banner (`#0b0f14` ground, gold accents read well).
- Tool: [`asciinema`](https://asciinema.org) + [`agg`](https://github.com/asciinema/agg) to render a
  GIF, or [`terminalizer`](https://github.com/faressoft/terminalizer). Keep the final GIF under ~3 MB
  so it loads fast on the README.

## Shot list (target ~15–20s)

1. `/ca:fix the statusline keeps running the old version after a plugin update`
   - Let the routing line land: *"Routing to tdd (bug variant) — a regression test before any fix."*
   - Show the failing test go **red for the right reason**, then the minimal fix, then green.
2. `/ca:commit`
   - Let the commit-gate checklist tick across: permission, branch, tests, secrets, behavioral proof,
     clean diff → committed. This is the satisfying beat — let it breathe.
3. `/ca:pr`
   - The reviewer fleet runs; **coverage-auditor BLOCKs** on an untested seam. Stop on the BLOCK for
     a beat so the viewer reads it.
   - (Optional, if it fits the time budget) resolve and re-run to green + PR opened.

## Capture & post

```sh
# record
asciinema rec demo.cast
# ...perform the shot list, then exit the shell to stop...

# render to gif
agg --theme 0b0f14,e6edf3 demo.cast docs/demo.gif
```

Then in `README.md`, replace the `<!-- DEMO ... -->` comment with:

```md
<div align="center"><img src="docs/demo.gif" alt="codeArbiter in motion — a gate blocks, the human resolves, the work goes green" width="900"></div>
```

Keep the alt text describing the BLOCK → resolve → green story; it's what someone scanning on a phone
reads before the GIF loads.
