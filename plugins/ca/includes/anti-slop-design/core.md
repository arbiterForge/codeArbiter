# anti-slop-design · core

The always-loaded decision layer. Load this for any design-bearing deliverable, then add the craft
and medium leaves the Design Read calls for.

> Section numbering is shared across the whole bundle, so this file skips some numbers on purpose:
> §4 typography, §5 color, §6 layout, §7 medium playbooks, and §9 images live in their own leaves.
> core owns §0-§3 (decision layer), §8 (universal tells), and §10 (core pre-flight).

## 0. Why slop happens (the one idea that explains every rule)

A language model produces output by regressing toward the statistical center of its training
distribution. For design, that center is the average of everything published, and that average is
generic, templated, and forgettable. "AI-slop" is not a style. It is the absence of a decision: the
model defaulting to the mean instead of choosing for *this* brief, *this* audience, *this* artifact.

Every rule in this bundle forces a deliberate move off the center. When you reach for the first thing
that "looks designed," you are reaching for the center. Excellence lives in the specific, the
considered, and the slightly uncomfortable choice a generic generator would never make.

Two corollaries that govern everything else:

- **A default chosen without a reason is a tell.** Inter, a centered hero, three equal cards, a purple
  gradient, skill bars on a resume, a pie chart: none is wrong in isolation. They are wrong as
  *reflexes*. If you cannot say in one sentence why a choice fits this brief, it is slop.
- **Consistency is cheap credibility; novelty is expensive credibility.** Locking one accent color,
  one corner radius, one type system costs nothing and reads as intentional. A striking layout costs
  judgment and can fail. Spend the cheap credibility everywhere; spend the expensive kind only where
  the brief earns it.

## 1. The Prime Directive: read the brief before you generate

Before producing anything, establish a one-line **Design Read**. Do it every time, internally.
Surface it only when it helps the user follow your choices; in a mid-task or CLI context a silent read
usually beats a printed preamble.

> "Reading this as a `<medium>` for `<audience>`, in a `<register>` register, leaning toward a
> `<aesthetic family>`."

Read the signals in order: **medium** (doc / chart / slide / resume / web / report), **audience**
(who decides, who scans, who parses it with software), **register** (institutional vs. expressive),
**existing assets** (brand color, logo, type, prior templates), **quiet constraints** (accessibility,
regulated industry, ATS, projection, print). Constraints override taste.

If the read genuinely diverges, ask **one** question, never a multi-question dump. If you can infer
confidently, declare the read and proceed.

## 2. The Dials

After the read, set four dials. Every density, layout, and emphasis decision in the bundle is gated by
them. Use these names; do not invent aliases.

- **`STRUCTURE`** (1-10): 1 = rigid symmetry and grid, 10 = asymmetric and expressive.
- **`DENSITY`** (1-10): 1 = airy/gallery, 10 = packed/cockpit.
- **`REGISTER`** (1-10): 1 = austere/institutional/legal, 10 = playful/consumer/brand.
- **`MOTION`** (1-10): *interactive media only*. 1 = static, 10 = cinematic. **N/A and ignored for any
  printed or static artifact** (PDF, docx, slide export, resume).

### 2.A Inference from the read

| Brief reads as | STRUCTURE | DENSITY | REGISTER | MOTION |
|---|---|---|---|---|
| Legal / compliance / regulated / public-sector | 2-3 | 4-6 | 1-2 | 1-2 |
| Technical review / due diligence / whitepaper | 3-5 | 6-8 | 2-4 | 2-3 |
| Executive brief / board deck | 4-6 | 3-5 | 3-5 | 3-5 |
| Resume / CV | 3-5 | 5-7 | 2-4 | n/a |
| Dashboard / analytics | 3-5 | 7-9 | 3-5 | 3-6 |
| Editorial / report-as-narrative | 5-7 | 3-5 | 4-6 | 3-5 |
| Consumer / product landing | 7-9 | 3-5 | 6-8 | 6-8 |
| Agency / portfolio / experimental | 8-10 | 3-4 | 7-9 | 7-10 |

The values are a starting point, not a script. A regulated brief with a strong brand can still earn
REGISTER 4. The point is to choose, and to be able to defend the choice.

### 2.B What each dial actually changes

A dial is useless if it does not change an output. Concretely:

- **`STRUCTURE`** drives composition: low → centered, symmetric, single grid; high → asymmetric, split
  composition, deliberate off-grid moments. Above 4, drop the centered-everything default (see layout
  §6.B).
- **`DENSITY`** drives whitespace and elements-per-screen: low → generous margins, few items, card
  chrome; high → tight rows, more per screen, drop card chrome and let data breathe (layout §6.C).
- **`REGISTER`** drives tone of type, color, and copy: low → restrained faces, single muted accent,
  literal copy; high → expressive display type, a bolder accent, more voice.
- **`MOTION`** drives animation budget on interactive media only: low → state-change feedback only;
  high → composed reveals and transitions. Ignored for static artifacts.

### 2.C When dials conflict

Resolve in this order: **quiet constraints (accessibility, ATS, print, regulated) > REGISTER > the
rest.** A legal brief with a strong brand (high REGISTER pull, low REGISTER constraint) resolves
toward the constraint: restrained, with the brand expressed in the one accent and the type, not in
layout fireworks.

## 3. Universal anti-slop laws (every medium, no exceptions)

These apply to a resume, a chart, a slide, and a landing page equally.

### 3.A The em-dash rule

Banned: the em-dash (`—`) and the en-dash (`–`) used as a **sentence-level separator in generated
prose** — headlines, body, captions, labels, button text, slide titles, marketing copy. That specific
use is the single highest-signal tell of machine-generated text in current testing, and it is the
first thing a reader's pattern-matcher flags. Restructure instead: split into two sentences with a
period, use a comma, parentheses, or a colon.

This is a scoped ban, not a blanket glyph ban. The following are **exempt** and never findings:

- **Quoted content** — a quote, citation, or excerpt from a user, source, or document that itself uses
  the dash.
- **Code and string literals** — anything inside code blocks, identifiers, or literal strings.
- **Math** — minus sign, and en-dash where it is correct typography.
- **File paths, URLs, and identifiers** that contain the character.
- **Proper nouns** — a brand, product, or publication title that legitimately contains a dash.
- **Numeric and date ranges** where the en-dash is correct typography (`pp. 12–18`, `2019–2024`).

The reviewer BLOCKs only on the banned case (a dash as a prose sentence-separator); an exempt
occurrence is not a finding. A stray separator dash in otherwise-fine copy is a fix, not a
catastrophe — restructure it and move on.

### 3.B Copy self-audit (read every visible string before shipping)

Flag and rewrite any string that is:

- **A filler verb or empty intensifier, in metaphorical or marketing use.** Flagged: *elevate,
  unleash, seamless, seamlessly, leverage, revolutionize, empower, streamline, robust, cutting-edge,
  next-gen, game-changing, supercharge, unlock, harness, navigate, dive into, delve, tapestry, realm,
  landscape, in today's fast-paced world.* Replace with concrete verbs that say what happens.
  **Literal and technical uses pass and are never findings:** "robust error handling," "navigate to
  `/home`" or `router.navigate`, a test "harness," "leverage" in its finance sense, "unlock" a screen
  or feature, "the deployment landscape" as a literal map of environments. The tell is the empty
  marketing gesture, not the word.
- **A rhetorical AI cadence.** The "it's not just X, it's Y" construction; "whether you're A, B, or C";
  opening on a rhetorical question; the rule-of-three on every list. One is fine. The *pattern*
  repeating is the tell.
- **Monotone rhythm.** AI prose tends toward sentences of even, medium length. Vary it. A short
  sentence after two long ones reads human. Uniform rhythm reads generated.
- **A fabricated-precise number** (see 3.D).
- **Grammatically broken or hallucinated cleverness.** Wordplay that does not parse, forced metaphors,
  fake-humble craftsman labels ("field notes," "on our bench," "loose plates"). When unsure whether a
  phrase earns its place, use the plain functional version. Boring-but-correct beats clever-but-wrong.

### 3.C Generic-placeholder ban

- **Names:** never "John Doe," "Jane Doe," "Sarah Chen," "Jack Su." Use realistic, locale-appropriate
  names. A deliberately-sample identity is fine when **marked** the same way a sample number is (see
  3.D): an explicit `example`/`sample` tag or a `<!-- sample -->` comment. The tell is a generic
  placeholder shipping as if it were real; a marked sample is not.
- **Brands:** never "Acme," "Nexus," "SmartFlow," "Cloudly," "TechCorp." Invent names that sound real
  for the sector, or use real ones where appropriate. Mark sample brands as above.
- **Avatars/logos:** no egg-silhouette avatars, no generic user-icon glyphs, no plain text wordmarks
  where a real logo or a designed monogram belongs.
- **Stock clichés:** no handshake photo, no diverse-team-at-whiteboard, no glowing-brain-AI image, no
  arrow-hitting-target.

### 3.D Data and number integrity (this is correctness, not taste)

Fabricated precision is a credibility failure, and in a technical review or report it can be a factual
one.

- Numbers like `92%`, `4.1x`, `47.2%`, `5.8mm` are acceptable **only** if they come from real data, or
  are explicitly marked illustrative (`example`, `sample`, `<!-- mock -->`).
- Do not invent benchmark figures, spec values, or metrics to make a page "feel precise." If you do
  not have the number, say so or omit it.
- Real data is messy. **When simulating** realistic data, avoid suspiciously round figures (`50%`,
  `99.99%`, `1,000,000`); real distributions are lumpy. This heuristic applies only to invented or
  illustrative data. A real round number (a genuine 50/50 split, a real 1,000,000 row count, an SLA
  literally specified as 99.99%) is fine and is never a finding.
- Label estimates as estimates. A reader who later finds an invented number stops trusting the whole
  document.

### 3.E The four consistency locks

Pick once, apply everywhere, audit before shipping. These are the **default**; a high-`STRUCTURE` or
high-`REGISTER` brief (portfolio, editorial, experimental) may override a lock where the expressive
move is the point — a deliberate second accent, a composed theme switch — provided the override is a
documented rule applied consistently, not a one-off accident. State the override as a visible
artifact-level note (a design-intent comment or a stated convention) so a reviewer can verify it, the
same discipline used to mark a sample value in 3.C/3.D. The lock is the floor; breaking it costs the
expensive credibility from §0, so spend it only where the brief earns it.

1. **Color lock.** One accent color across the whole artifact. A warm-grey report does not grow a blue
   callout box on page 7. A chart palette does not change between figures.
2. **Shape lock.** One corner-radius / border treatment system. Sharp, soft, or pill, chosen once.
   Mixed only under a documented rule applied everywhere.
3. **Type lock.** One display family, one body family, optionally one mono. Emphasis comes from weight
   and italic of the *same* family, never from a foreign font for one word.
4. **Theme lock.** One light/dark/print theme for the whole artifact. No section inverts mid-scroll
   unless it is a single, deliberate, composed switch.

### 3.F Cut ruthlessly

Slop is often just **too much**. Every section earns its place or is deleted. A 20-row table, a
12-bullet slide, a 6-paragraph hero, a 30-item award list: these are layout failures, not content. The
fix is a different component (group, summarize, link to detail), not a longer list.

## 8. Universal AI-tells (cross-medium quick-scan)

Each is banned *as a default*; the brief can override any with a reason. Medium-specific tells live in
the medium leaves.

**Punctuation and copy**
- Em-dash / en-dash as a prose sentence-separator (3.A): banned, with the 3.A exemptions.
- Filler verbs in marketing use and "fast-paced world" cadence (3.B).
- "It's not just X, it's Y"; "whether you're A or B"; rhetorical-question openers; rule-of-three on
  everything.
- Generic names and brands: John/Jane Doe, Acme, Nexus, TechCorp (3.C).
- Fake-precise numbers (3.D); suspiciously round numbers.
- Generic step labels: "Step 1 / Phase 1 / Stage 1." The step content is the label.
- Performative-craftsman section labels: "field notes," "on the bench," "loose plates," "quietly
  trusted by."

**Visual (cross-medium)**
- AI-purple / blue glow gradient; neon outer glows.
- Centered-everything composition.
- Pure `#000` / `#fff` large fills.
- Generic stock clichés (handshake, whiteboard team, glowing brain).
- Egg-silhouette avatars and generic user-icon glyphs.
- Rainbow categorical palettes.

**Structural**
- Eyebrow label above every section.
- Every section the same layout family.
- Decorative status dots before every list item / nav link.
- Locale/time/weather atmospheric strips with no real function.
- "Scroll" cues and version stamps (`v0.6`, `BETA`) used as decoration.
- Section-number eyebrows (`00 / INDEX`, `001 · Capabilities`).

## 10. Core pre-flight (run before delivering anything)

If a box cannot be honestly ticked, it is not done. Each medium leaf adds its own slice.

- [ ] Design Read established (medium, audience, register, aesthetic family); internal if not surfaced.
- [ ] Dial values chosen with a reason, not silently defaulted.
- [ ] **No em-dash / en-dash used as a prose sentence-separator** (the 3.A exemptions are fine).
- [ ] Copy self-audit done: no marketing-filler verbs, no AI cadence, no monotone rhythm, no
  hallucinated cleverness.
- [ ] No generic placeholder names, brands, avatars, or stock clichés.
- [ ] Every number is real, marked illustrative, or omitted. No fabricated precision.
- [ ] Color lock, shape lock, type lock, theme lock all hold across the whole artifact.
- [ ] First impression delivers the point in the space available.
- [ ] Content cut ruthlessly; no data-dump where a different component belongs.
- [ ] No universal tell (§8) ships without a brief-driven reason.
