/**
 * redactor.ts — codeArbiter's outbound-boundary secret redactor.
 *
 * The single security control that scrubs secret-shaped content before it
 * crosses the trust boundary to the third-party Zen API (injected file bodies,
 * gate-output tails) and the secret-bearing-filename denylist that keeps such
 * files from being read at all. Extracted verbatim from farm.ts (v2.rev.0020 /
 * architecture-003) — this is a move, not a rewrite.
 *
 * DELIBERATELY DISTINCT in shape from the hook-side _hooklib.SECRET_RE commit
 * gate (architecture-001): SECRET_LINE here is BROAD (over-redaction is the safe
 * direction for content leaving the trust boundary); SECRET_RE is NARROW. The
 * AGREEMENT region between them is pinned by
 * plugins/ca/hooks/secret-detection-corpus.json — asserted against redactSecrets
 * here (farm.unit.test.ts) and against SECRET_RE in test_hooklib.py, so neither
 * side can silently regress.
 */

// AC-05 secret redaction. NEW code — there is no existing in-code secret sweep
// to reuse (the repo's sweep is the manual/hook layer per tech-stack.md). This
// is the exact secret-pattern set from tech-stack.md "Secrets scan", applied
// case-insensitively. Any single line that matches a pattern is replaced
// WHOLESALE with a `[REDACTED]` marker rather than surgically excising the
// matched span — over-redaction is the safe direction, and the line is the
// smallest unit guaranteed to contain the full secret value (e.g. the trailing
// token after `api_key =`).
//
// SPAN-AWARE for PEM blocks (FINDING 1). A purely per-line redactor is unsafe
// for multi-line secrets: a PEM private key's `-----BEGIN ... PRIVATE KEY-----`
// header matches the trigger word, but the base64 BODY lines carry no trigger
// word, so a per-line pass would transmit the key material. When a
// `-----BEGIN ... -----` delimiter line is seen, we redact the WHOLE block
// through the matching `-----END ... -----` delimiter (or to end-of-content if
// no END is present) as a single unit. Single-line trigger-word matches keep
// the existing per-line behavior. Matching, never transmitting a matched
// secret, is the invariant — see spec AC-05 / D5.
// Trigger words plus known high-entropy key prefixes (AWS / GitHub). This
// outbound redactor is DELIBERATELY DISTINCT in shape from the hook-side
// _hooklib.SECRET_RE commit gate (architecture-001): SECRET_LINE is BROAD — a
// bare trigger word anywhere on a line redacts the whole line, because over-
// redaction is the safe direction for content crossing the trust boundary;
// SECRET_RE is NARROW — it requires a quoted-literal assignment so it does not
// fire on every `token:` reference in committed source. They therefore disagree
// by design on bare-keyword lines. What is pinned is the AGREEMENT region:
// plugins/ca/hooks/secret-detection-corpus.json lists real secret shapes both
// must flag and benign lines both must pass, asserted against SECRET_LINE here
// (farm.unit.test.ts) and against SECRET_RE in test_hooklib.py, so neither side
// can silently regress on it.
const SECRET_LINE = /(api[_-]?key|token|secret|password|BEGIN.*PRIVATE|sk-ant|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})/i;
// PEM-style armor delimiters. BEGIN opens a span; END closes it. Matched
// independently of SECRET_LINE so even a `-----BEGIN CERTIFICATE-----` (no
// trigger word) is span-redacted — armored material is opaque, redact it whole.
const PEM_BEGIN = /^-----BEGIN .*-----\s*$/;
const PEM_END = /^-----END .*-----\s*$/;
const REDACTION_MARKER = "[REDACTED — secret-pattern match removed before transmission]";

// Data-minimization (defence in depth ahead of per-line/span redaction): some
// filenames are secret-bearing by convention and should never be read into the
// injected context AT ALL, regardless of whether their individual lines trip a
// trigger word. Matched on the BASENAME so a nested `config/.env.production` or
// `keys/id_rsa` is caught too. If a file is denylisted its contents are simply
// never read — the strongest form of non-transmission.
const SECRET_FILENAME_DENYLIST: RegExp[] = [
  /^\.env$/i, // .env
  /^\.env\..+$/i, // .env.local, .env.production, ...
  /\.pem$/i, // *.pem
  /\.key$/i, // *.key
  /^id_rsa(\..+)?$/i, // id_rsa, id_rsa.pub, id_rsa.bak
  /^id_ed25519(\..+)?$/i, // id_ed25519, id_ed25519.pub
  /^id_ecdsa(\..+)?$/i, // id_ecdsa, id_ecdsa.pub
  /\.p12$/i, // PKCS#12 keystore
  /\.pfx$/i, // PKCS#12 keystore (Windows)
];

export function isSecretBearingFilename(relPath: string): boolean {
  const base = relPath.split(/[\\/]/).pop() ?? relPath;
  return SECRET_FILENAME_DENYLIST.some((re) => re.test(base));
}

export function redactSecrets(contents: string): string {
  const lines = contents.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (PEM_BEGIN.test(line.trim())) {
      // Span redaction: collapse BEGIN..END (inclusive) to one marker. If no
      // END is found, redact through end-of-content — never let an unterminated
      // armored body trickle out.
      out.push(REDACTION_MARKER);
      i++;
      while (i < lines.length && !PEM_END.test(lines[i].trim())) i++;
      // i now points at the END line (consumed by the span) or past the end.
      continue;
    }
    out.push(SECRET_LINE.test(line) ? REDACTION_MARKER : line);
  }
  return out.join("\n");
}
