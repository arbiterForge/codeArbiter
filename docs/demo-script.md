# Demo recording walkthrough: codeArbiter in motion

The single highest-impact asset the README is missing is **~15 seconds of a gate actually firing**.
This is a complete, beginner-friendly walkthrough for recording it on **Windows** with
[`terminalizer`](https://github.com/faressoft/terminalizer), with no prior GIF experience assumed.
Follow it top to bottom. When you're done, the GIF lands at `docs/demo.gif` and you uncomment one line in
`README.md`.

If terminalizer ever fights you (Windows can be fussy about it; see [Troubleshooting](#troubleshooting)),
there's a zero-setup fallback at the bottom using a point-and-click app instead.

---

## What you're filming (and why this exact sequence)

Don't film a smooth happy path. **The friction is the feature.** The beat that sells codeArbiter is:
a gate **BLOCKS**, you **resolve** it, the work goes **green**. Everything in the shot list below
builds to that moment.

You'll type three commands into a Claude Code session and let codeArbiter respond:

1. `/ca:fix the statusline keeps running the old version after a plugin update`
   → it routes to TDD, writes a **failing** test, then the fix, then green.
2. `/ca:commit`
   → the commit-gate checklist ticks across (permission, branch, tests, secrets, behavioral proof).
3. `/ca:pr`
   → the reviewer fleet runs and **coverage-auditor BLOCKs** on an untested seam. ← *this is the shot.*

(Use a throwaway repo that's already opted in via `/ca:init`, with a small real bug to fix. The demo
is most honest if it's a real run, not faked.)

---

## Step 0. One-time: confirm your tools (you already have Node)

You already have Node and npm installed (v24 / v11 as of this writing), so you can skip installing them.
Just confirm in a terminal:

```powershell
node --version    # expect v18 or newer
npm --version
```

Then install terminalizer once, globally:

```powershell
npm install -g terminalizer
terminalizer --version    # confirms it installed
```

> If `terminalizer` isn't recognized after install, close and reopen your terminal so PATH refreshes.

---

## Step 1: Start recording

Pick a working folder (it doesn't matter where; the recording is just a file), then:

```powershell
terminalizer record demo
```

This drops you into a **new shell that is being recorded.** Everything you type from here is captured.
A file called `demo.yml` will be written when you stop.

> Tip: make your terminal window a comfortable size *before* recording, about **110 columns × 30 rows**.
> A dark theme reads best (it'll match the GIF theme you set in Step 3).

---

## Step 2: Perform the demo, then stop

Inside that recording shell:

1. Launch Claude Code (`claude`) in your throwaway opted-in repo.
2. Run the three commands from the shot list above, **pausing a beat** after each response lands so a
   viewer can read it. Linger an extra second on the **BLOCK** in step 3; that's the payoff frame.
3. When the PR step finishes, **stop the recording by exiting the shell**:

```powershell
exit
```

terminalizer prints something like `Successfully Recorded` and saves **`demo.yml`** in the current
folder. (That `.yml` is an editable recording, not the GIF yet. You can re-render it as many times as
you like without re-recording.)

---

## Step 3: Tidy the recording (theme + pacing)

Open `demo.yml` in any editor. You don't need to understand all of it; just change a few keys near the
top so the GIF is on-brand and snappy (the box-drawing comments in the file are decorative; leave them):

```yaml
# ── make it snappy ─────────────────────────────────────────
frameDelay: auto        # keep real typing rhythm
maxIdleTime: 1200       # auto-compress any pause longer than 1.2s (kills dead air)
cols: 110
rows: 30

# ── match the codeArbiter banner palette ───────────────────
theme:
  background: "#0b0f14"   # banner ground
  foreground: "#e6edf3"   # banner text
  cursor: "#e3b341"       # banner gold
  black:   "#0b0f14"
  red:     "#d97757"      # the "forge"/danger orange
  green:   "#3da639"
  yellow:  "#e3b341"      # gold
  blue:    "#2b7489"
  magenta: "#bc8cff"
  cyan:    "#39c5cf"
  white:   "#e6edf3"
```

Save the file. (`frameDelay`/`maxIdleTime` are the two that matter most; they decide how long the GIF
runs. If your GIF comes out too long, lower `maxIdleTime`.)

If a chunk at the very start or end is boring (e.g. the shell launching), you can delete those entries
from the `records:` list at the bottom of the file; each entry is one captured frame with a `delay`
and `content`. Optional; the `maxIdleTime` trick usually does enough.

---

## Step 4: Render the GIF

From the same folder:

```powershell
terminalizer render demo -o docs/demo.gif
```

The first render downloads a small headless browser and may take a minute; that's normal. When it
finishes you'll have **`docs/demo.gif`**.

**Keep it lean.** Aim for **under ~3 MB** so the README loads fast. If it's too big:
- lower `maxIdleTime` (e.g. `800`) and re-render; shorter GIF = smaller file;
- reduce `cols`/`rows` slightly;
- trim boring frames from the `records:` list (Step 3).

Preview it by double-clicking `docs/demo.gif` in File Explorer, or drag it into a browser tab.

---

## Step 5: Put it in the README

Open `README.md` and find this comment near the top:

```html
<!-- DEMO: once recorded, replace this comment with the in-motion GIF. Recording shot list in docs/demo-script.md
<div align="center"><img src="docs/demo.gif" alt="codeArbiter in motion: a gate blocks, the human resolves, the work goes green" width="900"></div>
-->
```

Delete the `<!--` line and the closing `-->` line, leaving just the `<div>…</div>` in the middle. That
"uncomments" the GIF so it renders on GitHub. Keep the `alt` text; it's what someone on a phone reads
before the GIF loads.

Then ship it the normal way: `/ca:chore` (it's a docs change) → `/ca:commit` → `/ca:pr`. The GIF is a
new file under `docs/` (not `plugins/ca/`), so **no version bump is required**.

---

## Troubleshooting

- **`terminalizer: command not found` after install:** reopen the terminal (PATH refresh). Still
  stuck? Run it via `npx terminalizer record demo`.
- **Install fails compiling a native module:** terminalizer pulls in a PTY library. Usually retrying
  `npm install -g terminalizer` works; if not, use the fallback below.
- **`render` errors or hangs downloading the browser:** corporate network/proxy can block it. Try
  again on an open network, or use the fallback below.
- **GIF is huge (>5 MB):** almost always too much idle time. Lower `maxIdleTime`, re-render. Length is
  the #1 driver of file size.

### Zero-setup fallback: ScreenToGif (point-and-click)

If terminalizer isn't worth the fight, this needs no command line at all:

1. Install **ScreenToGif** (free) from the Microsoft Store.
2. Open it → **Recorder** → drag the frame over your Claude Code terminal window.
3. Click **Record**, perform the shot list, click **Stop**.
4. The editor opens → delete dead frames to trim → **File → Save as → Gif** → save to `docs/demo.gif`.

It captures your real window (your font/theme) rather than a re-rendered terminal, so set a dark theme
first. Same Step 5 afterward.
