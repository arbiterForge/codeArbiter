/**
 * Unit tests for redactor.ts — the outbound-boundary secret redactor.
 *
 * Scoped to the SPAN redaction path, the filename denylist, and the SECRET_LINE
 * rules nothing else in the tree pins.
 *
 * Why a unit file when farm.test.ts already has a PEM case: that case
 * (`redacts a multi-line PEM private key as a span`) drives the whole dispatcher
 * through `spawn()`, so it proves the behaviour end-to-end but exercises the
 * redactor in a CHILD process — which the v8 coverage provider does not
 * instrument. It also plants exactly one shape: unindented armor, at column 0,
 * well-formed, with a non-empty body. The regressions that actually leak key
 * material are the near misses around that shape, and they are what this file
 * pins.
 *
 * Cases that are the SOLE killer of a mutation say so. Cases kept as canonical
 * examples say that instead of claiming a kill they do not make — two such
 * comments were wrong in the first cut of this file and are worse than no
 * comment, because they send the next reader at the wrong mutation.
 *
 * Two adversarial passes over 87 hand mutants shaped this file. The first found
 * 16 of 21 surviving while the module reported 100% lines / 87.5% branches; the
 * second found a real off-by-one and an unpinned anchor still surviving the
 * rewrite. Coverage is not the property under test here — "does the assertion
 * fail when the source is wrong" is.
 */
import { describe, expect, it } from "vitest";
import { isSecretBearingFilename, redactSecrets } from "./redactor.ts";

const MARKER = "[REDACTED — secret-pattern match removed before transmission]";

// The armor delimiters are ASSEMBLED AT RUNTIME rather than written as literals.
// A committed PEM header line is reported by gitleaks' `private-key` rule — the
// header alone is enough, no body required, which is why this comment does not
// spell one either. .gitleaks.toml is deliberately default-deny, so waiving it
// would mean pinning an anchored copy of this file's exact block shape, which
// then has to be re-derived every time the array is reformatted (see the
// farm.test.ts waiver in that file for what that costs). redactSecrets receives
// a byte-identical string either way, so there is nothing to buy with a waiver.
const ARMOR = "-".repeat(5);
const begin = (label: string): string => `${ARMOR}BEGIN ${label}${ARMOR}`;
const end = (label: string): string => `${ARMOR}END ${label}${ARMOR}`;
const PRIVATE_KEY = "RSA PRIVATE KEY";

// Body lines deliberately carry NO trigger word, so a purely per-line redactor
// would transmit them verbatim. That is the whole point of span redaction. They
// are also deliberately NOT base64-shaped — realistic key material would trip
// the hosted scanner for no gain, since the redactor never inspects the body.
const BODY = [
  "SPANBODYLINEONE0000000000000000000000000000000",
  "SPANBODYLINETWO1111111111111111111111111111111",
  "SPANBODYLINETHREE22222222222222222222222222===",
];

describe("redactSecrets — PEM span redaction", () => {
  it("collapses a BEGIN..END block to exactly one marker", () => {
    // CANONICAL EXAMPLE, not a sole killer — every mutation it catches is also
    // caught below. It stays because the file should show what correct looks
    // like before it shows nine ways to break it, and because exact
    // whole-output equality is the assertion style everything else here uses:
    // a per-line redactor would emit five markers, so the SHAPE of the output
    // is what separates span redaction from the per-line fallback.
    const out = redactSecrets(
      ["const pem = `", begin(PRIVATE_KEY), ...BODY, end(PRIVATE_KEY), "`;"].join("\n"),
    );

    expect(out).toBe(["const pem = `", MARKER, "`;"].join("\n"));
  });

  it("stops the span at the END delimiter and preserves the content after it", () => {
    // Sole killer: dropping `!PEM_END.test(...)` from the while condition, which
    // runs the span to end-of-content. The key is still redacted under that
    // mutant, so only the SURVIVORS distinguish it from correct behaviour.
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        ...BODY,
        end(PRIVATE_KEY),
        "export const PORT = 8080;",
        "export const NAME = 'after-the-span';",
      ].join("\n"),
    );

    expect(out).toBe([MARKER, "export const PORT = 8080;", "export const NAME = 'after-the-span';"].join("\n"));
  });

  it("redacts through end-of-content when the block is never terminated", () => {
    // Sole killer: the `i < lines.length` bound. A truncated armored body is
    // still key material, so an unterminated block takes the rest of the
    // content with it — `trailing = 1;` is INSIDE the span.
    const out = redactSecrets([begin(PRIVATE_KEY), ...BODY, "trailing = 1;"].join("\n"));

    expect(out).toBe(MARKER);
  });

  it("consumes exactly the delimiters of an EMPTY block, dropping no following line", () => {
    // Sole killer: `i++` -> `i += 2` at the span advance. With no body line
    // between the delimiters, an over-advancing span walks past END and eats
    // the line after it — output looks correctly redacted while a line of the
    // caller's content has silently vanished. Only a zero-body block exposes
    // it; every other case here has body lines absorbing the extra step.
    const out = redactSecrets([begin(PRIVATE_KEY), end(PRIVATE_KEY), "after = 8;"].join("\n"));

    expect(out).toBe([MARKER, "after = 8;"].join("\n"));
  });

  it("spans INDENTED armor, whose body a column-0-only matcher transmits", () => {
    // Sole killer: removing `.trim()` from EITHER delimiter test. Both survived
    // the first cut of this file because every delimiter in it sat at column 0.
    // Indented armor is routine — a PEM inside a YAML block scalar, or inside an
    // indented template literal.
    //
    // Without the BEGIN trim: the header still trips SECRET_LINE's
    // `BEGIN.*PRIVATE` and is redacted per-line, but the indented BODY carries
    // no trigger word and ships verbatim. That is the leak this pins.
    // Without the END trim: the span never closes and swallows `after = 3;`.
    const out = redactSecrets(
      ["  " + begin(PRIVATE_KEY), "  " + BODY[0], "  " + end(PRIVATE_KEY), "after = 3;"].join("\n"),
    );

    expect(out).toBe([MARKER, "after = 3;"].join("\n"));
  });

  it("does not let a body line's INLINE end-armor close the span early", () => {
    // Sole killer: dropping PEM_END's `^` anchor. Under that mutant the span
    // closes on the body line below, and the two lines after it — real key
    // body — ship.
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        `${BODY[0]} ${end(PRIVATE_KEY)}`,
        BODY[1],
        BODY[2],
        end(PRIVATE_KEY),
        "after = 2;",
      ].join("\n"),
    );

    expect(out).toBe([MARKER, "after = 2;"].join("\n"));
  });

  it("does not let an END delimiter with TRAILING prose close the span early", () => {
    // Sole killer: dropping PEM_END's `$` anchor, and equally dropping its
    // trailing `-----`. The mirror of the BEGIN case below, and its absence was
    // a live leak: a prose line inside an armored block closes the span, and
    // BODY[1] plus the real END delimiter ship.
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        BODY[0],
        `${end("CERTIFICATE")} (as shown above)`,
        BODY[1],
        end(PRIVATE_KEY),
        "after = 7;",
      ].join("\n"),
    );

    expect(out).toBe([MARKER, "after = 7;"].join("\n"));
  });

  it("does not open a span on a BEGIN delimiter carrying TRAILING prose", () => {
    // Sole killer: dropping PEM_BEGIN's `$` anchor. (The `\s*` before it is not
    // killable — `.trim()` has already stripped trailing whitespace by the time
    // the regex runs, so `\s*$` is equivalent to `$`. Not cited as a kill.)
    // Under the mutant a documentation line opens a span and swallows the rest
    // of the file. CERTIFICATE is used so SECRET_LINE has no trigger word
    // either — the line must survive VERBATIM.
    const line = `${begin("CERTIFICATE")} <- what the header looks like`;
    const out = redactSecrets([line, "after = 5;"].join("\n"));

    expect(out).toBe([line, "after = 5;"].join("\n"));
  });

  it("does not open a span on a BEGIN delimiter carrying LEADING prose", () => {
    // Sole killer: dropping PEM_BEGIN's `^` anchor. Needs its own case: here the
    // armor sits at the END of the line, so the `$` anchor still matches and
    // only `^` stands between a comment and a span that swallows the remainder
    // of the file.
    const line = `// the header shape is ${begin("CERTIFICATE")}`;
    const out = redactSecrets([line, "after = 6;"].join("\n"));

    expect(out).toBe([line, "after = 6;"].join("\n"));
  });

  it("spans armor that carries no trigger word at all", () => {
    // Sole killer: folding span detection into the trigger-word test (i.e.
    // requiring SECRET_LINE to match before PEM_BEGIN is consulted). CERTIFICATE
    // matches no SECRET_LINE pattern, so this block reaches the span path only
    // via PEM_BEGIN — armored material is opaque and is redacted whole whether
    // or not it announces itself.
    const out = redactSecrets(
      [begin("CERTIFICATE"), ...BODY, end("CERTIFICATE"), "done = true;"].join("\n"),
    );

    expect(out).toBe([MARKER, "done = true;"].join("\n"));
  });

  it("redacts a per-line trigger inside a span's trailing content, not just the span", () => {
    // Sole killer: inverting the per-line ternary at the end of the loop body.
    // After a span closes, ordinary per-line handling must resume — a secret on
    // a later line is not covered by the block above it.
    const out = redactSecrets(
      [begin("CERTIFICATE"), BODY[0], end("CERTIFICATE"), "const token = abc;", "tail = 9;"].join("\n"),
    );

    expect(out).toBe([MARKER, MARKER, "tail = 9;"].join("\n"));
  });

  it("redacts an INLINE delimiter mention as one line, not a span", () => {
    // Sole killer: deleting `BEGIN.*PRIVATE` from SECRET_LINE. Neither anchor
    // is what this pins — the trailing " inline" already fails the `$` anchor,
    // so `^` never participates. An earlier version of this file claimed the
    // `^` kill here and was wrong; the leading-prose case above owns that.
    // What is unique here: the line is not armor, so only the trigger word
    // stands between a pasted key header and transmission.
    const out = redactSecrets(
      [`the header reads ${begin(PRIVATE_KEY)} inline`, "next = 'must survive';"].join("\n"),
    );

    expect(out).toBe([MARKER, "next = 'must survive';"].join("\n"));
  });

  it("passes a lone END delimiter through, carrying no span state into it", () => {
    // CANONICAL, not a sole killer. Documents a design decision that was
    // previously unasserted: an END with no BEGIN is not armor and holds no key
    // material, so it survives verbatim rather than opening or closing anything.
    const out = redactSecrets([end(PRIVATE_KEY), "after = 4;"].join("\n"));

    expect(out).toBe([end(PRIVATE_KEY), "after = 4;"].join("\n"));
  });

  it("preserves CR on CRLF input rather than silently rewriting the line ending", () => {
    // Sole killer: `contents.split("\n")` -> `split(/\r?\n/)`. The redactor
    // splits on LF and rejoins on LF, so a CRLF caller gets its CRs back on the
    // lines that survive. Under the mutant every CR is stripped and the
    // redactor becomes a line-ending rewriter — on Windows, where this runs,
    // that silently reformats content it was only asked to redact.
    const out = redactSecrets(["a\r", "const token = x;\r", "b"].join("\n"));

    expect(out).toBe(["a\r", MARKER, "b"].join("\n"));
  });
});

describe("redactSecrets — SECRET_LINE rules nothing else pins", () => {
  // farm.unit.test.ts pins the shared corpus (architecture-001) and the #439
  // shapes; `password`, AKIA, ghp_ and Bearer are genuinely covered there. These
  // four are NOT, and each was confirmed to survive tree-wide:
  //
  //   - `token` and the pattern's `i` flag have no fixture at all.
  //   - `glpat-` and the URL basic-auth rule MASK EACH OTHER: the only fixture
  //     exercising either is a clone URL that matches BOTH, so either rule can
  //     be deleted with the whole tree green. They are pinned separately here.
  it("redacts a bare `token` trigger word", () => {
    expect(redactSecrets("const token = abc;")).toBe(MARKER);
  });

  it("matches trigger words case-insensitively", () => {
    expect(redactSecrets("API_KEY = value")).toBe(MARKER);
    expect(redactSecrets("PASSWORD = value")).toBe(MARKER);
  });

  it("redacts a GitLab PAT prefix with no URL and no trigger word around it", () => {
    // EXACTLY 8 chars after the prefix — the rule's quantifier. A longer fixture
    // still matches under `{9}`, so it would not pin the boundary.
    expect(redactSecrets("GITLAB=glpat-AbCd1234")).toBe(MARKER);
  });

  it("redacts basic-auth credentials in a URL with no PAT prefix", () => {
    expect(redactSecrets("git clone https://ci:pw@example.com/repo.git")).toBe(MARKER);
  });

  it("leaves a URL with no credentials alone", () => {
    // The rule requires the colon-and-at shape, not merely an `@` in a URL.
    const line = "npm i https://example.com/@scope/pkg";
    expect(redactSecrets(line)).toBe(line);
  });

  // DELIBERATELY NOT PINNED: the URL rule's `+` quantifiers relaxed to `*`.
  // That mutant differs only on an empty user or password (`https://:@host`),
  // so it WIDENS the rule — the safe, over-redacting direction for an outbound
  // control — and killing it would need a benign fixture containing `://:@`,
  // which no real content carries. Recorded rather than papered over with an
  // assertion that pins nothing anyone would write.
});

describe("isSecretBearingFilename — basename denylist", () => {
  it.each([
    [".env"],
    ["config/.env.production"],
    // Both id_rsa and id_ed25519 need a BARE and a suffixed row: with only the
    // suffixed one present, making the `(\..+)?` group mandatory survives.
    ["keys/id_rsa"],
    ["keys/id_rsa.pub"],
    ["keys/id_ed25519"],
    ["keys/id_ed25519.pub"],
    ["keys/id_ecdsa"],
    ["store/keystore.p12"],
    ["store/keystore.pfx"],
    // BACKSLASH separator against an ANCHORED rule. The measurement platform is
    // Windows, and `split(/[\\/]/)` -> `split(/\//)` survived the entire tree on
    // the first cut of this file: the only backslash case then present was
    // `secrets\api.key`, which matches the SUFFIX rule `/\.key$/i` and so passes
    // whether or not the basename was ever extracted. Under that mutant a
    // denylisted private key is read and its contents cross the trust boundary.
    ["keys\\id_rsa"],
    // Retained despite the above: this is the ONLY `.key` deny row, so it is the
    // sole killer of deleting `/\.key$/i` outright.
    ["secrets\\api.key"],
  ])("denies %s", (relPath) => {
    expect(isSecretBearingFilename(relPath)).toBe(true);
  });

  it.each([
    // Each allow-case kills at least one rule-weakening mutation that no other
    // row kills. The `$`-anchor rows matter less than the deny rows — dropping
    // an end anchor WIDENS the denylist, and over-refusal is the safe direction
    // for this control — but a rule that quietly denies `notes.pem.txt` starves
    // the worker of legitimate context, so the boundary is still worth pinning.
    ["src/environment.ts"], //  `/^\.env$/i`      -> `/env/i`
    ["config/prod.env"], //     `/^\.env$/i`      -> `/\.env$/i`   (drops `^`)
    ["src/.environment"], //    `/^\.env$/i`      -> `/^\.env/i`   (drops `$`)
    ["config/apikey"], //       `/\.key$/i`       -> `/key$/i`     (escaped dot)
    ["secrets/api.key.bak"], // `/\.key$/i`       -> `/\.key/i`    (drops `$`)
    ["src/pemantle.ts"], //     `/\.pem$/i`       -> `/pem/i`
    ["notes.pem.txt"], //       `/\.pem$/i`       -> `/\.pem/i`    (drops `$`)
    ["store/keystore.p12.bak"], // `/\.p12$/i`    -> `/\.p12/i`    (drops `$`)
    [".env."], //               `/^\.env\..+$/i`  -> `.*`  (suffix must be non-empty)
  ])("allows %s", (relPath) => {
    expect(isSecretBearingFilename(relPath)).toBe(false);
  });

  it("matches on the basename, not anywhere in the path", () => {
    // A directory named `.env` must not condemn an ordinary file beneath it.
    expect(isSecretBearingFilename(".env/notes.md")).toBe(false);
    expect(isSecretBearingFilename("src/id_rsa/index.ts")).toBe(false);
  });

  it("is case-insensitive on both the name and the extension", () => {
    // Also the only `.pem` deny coverage, so it carries that rule's deletion.
    expect(isSecretBearingFilename("CONFIG/.ENV")).toBe(true);
    expect(isSecretBearingFilename("certs/SERVER.PEM")).toBe(true);
    expect(isSecretBearingFilename("keys/ID_RSA")).toBe(true);
  });
});
