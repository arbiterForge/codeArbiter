# 03 — No Windows-specific setup/caveats for Pi on the site

**Severity:** medium

**Page path:** missing page. Neither `getting-started/install.md`,
`getting-started/compatibility.md`, nor `guides/troubleshooting.md` on the
site mentions Windows process-tree cleanup, `windows-supervisor`, or any
OS-specific caveat for Pi. `plugins/ca-pi/helpers/windows-supervisor.js`
exists (sets `windowsHide: true`, implements Windows-specific child-process
supervision), and `docs/pi-parity-testing.md` / `docs/parity.md` reference a
committed Windows/macOS/Linux promotion matrix for Pi 0.80.5/0.80.6 — but
none of that is surfaced in end-user terms on the docs site.

**What the user was trying to do:** A Windows user installing `ca-pi` hits
child-process behavior (dispatch, cancellation, process-tree cleanup) that
differs from macOS/Linux and wants to know what's different and whether it's
supported/tested.

**What's missing:** A short "Windows notes" callout — confirming Windows is a
tested platform for Pi (per the promotion matrix), and explaining that child
Pi processes are supervised via a Windows-specific helper for reliable
cancellation/cleanup (no zombie processes on `Ctrl+C` or dispatch timeout).
Currently a Windows user has no signal this was even considered, let alone
tested, from the docs site alone.

**Remediation shape:** Add a "Windows" subsection to the (currently missing,
see finding 01) Pi install page and/or the Compatibility page, stating Windows
is a promoted/tested platform and briefly noting the supervised child-process
cleanup behavior.
