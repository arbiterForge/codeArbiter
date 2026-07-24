# anti-slop-design · typography

Load it whenever the medium renders text with chosen type (per the INDEX load map). The single
most-tested tell is the wrong typeface chosen by reflex. The right choice depends on the medium.

The rule is the **principle**, not the name: be able to say in one sentence why this face fits this
brief. The specific faces named below are *current* examples of reflexes and reasonable reaches; they
will age, and the "reach" lists are non-exhaustive starting points, not a closed menu to default to.
Defaulting to a published alternative list just recreates the reflex with a new name.

## 4.A Body text

- **On screen / web UI:** humanist or geometric sans for body. Avoid the current LLM-default face
  (`Inter`, at time of writing) *as a reflex*; it is acceptable when a neutral, system-standard feel is
  explicitly wanted, or for accessibility-first contexts. Reasonable current reaches (non-exhaustive):
  Geist, Outfit, Söhne, IBM Plex Sans, or a brand-appropriate face. The point is a face chosen for a
  reason, not the specific name.
- **In documents / print / PDF (reports, whitepapers, books):** a serif or a high-quality humanist
  sans for sustained reading is **best practice, not a tell**. Serif body text in a long report is
  correct typography. Pick a real text face (a Garamond, Source Serif, IBM Plex Serif, Charter, or a
  clean humanist sans) over the Office defaults (Calibri, Times New Roman) chosen without thought.
- **Measure:** 60-75 characters per line. Line-height 1.4-1.6 for body. Do not full-justify text that
  produces rivers; left-align unless you control hyphenation.

## 4.B Display / headings

- **Web and slides default to sans display.** Sans display is not "boring"; it is default for the same
  reason black is default in fashion. Reach: Geist Display, Cabinet Grotesk, PP Neue Montreal, GT
  Walsheim, Inter Display.
- **Serif display is allowed when justified** (genuinely editorial, luxury, publication, heritage, or a
  brand that names a serif) and you can say why this serif fits this brand. When justified, **do not
  default to the current LLM-favorite display serifs** (`Fraunces`, `Instrument Serif` at time of
  writing). Other current options, non-exhaustive: PP Editorial New, Reckless Neue, Tiempos Headline,
  Canela, Domaine Display. Pick for fit, do not just swap one default for another.
- **Emphasis within a headline** uses italic or bold of the *same* family. Injecting one serif word
  into a sans headline (or vice versa) is amateur.
- **Italic descenders:** any italic word containing `y g j p q` needs at least `1.1` line-height and a
  little bottom reserve so the descender is not clipped.

## 4.C Hierarchy

Build hierarchy with **weight, size, and space**, not with boxes, rules, and color on everything.
Three levels are usually enough: section, subsection, body. If everything is emphasized, nothing is.

## Tells (typography)

- Inter as a reflex body face on screen.
- Fraunces / Instrument Serif as the default display serif.
- A foreign font injected for a single emphasized word.
- Clipped italic descenders.
- Full-justified body with visible rivers.
