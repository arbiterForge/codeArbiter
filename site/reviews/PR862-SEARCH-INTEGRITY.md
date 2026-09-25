# PR862: complete search-bundle output

## Observed failure, not a weakened browser contract

At `0c989584f0bc14bdf95d62dc80b910bf85c0f0fb`, documentation workflow `36118130577`
completed generation, static rendering and the link audit. Browser job `108016944918`
passed 166 tests and failed six real full-text search checks. Its direct Pagefind
module import reported `SyntaxError: Unexpected end of input`; the ordinary search
interface correctly showed its retry state rather than invented results.

All six retained failure traces report a successful HTTP response for
`/pagefind/pagefind.js` with a server ETag identifying 32,768 bytes. This is an
incomplete served module, not evidence that the query returned no matches. The
same locked Pagefind 1.5.2 engine generates a 45,555-byte valid module in the local
reproduction. The search component, ranking expectations and six failing browser
assertions are unchanged.

The native writer's exact failure mechanism remains unconfirmed: 25 local
write-and-close trials returned complete modules. The installed Starlight integration
awaits `writeFiles()` and then closes the Pagefind service; the installed service's
close implementation kills its child process. A completion/shutdown race is a
hypothesis, not a reproduced upstream defect. This correction removes dependence
on that native disk-write boundary instead of asserting that a sleep or another
successful retry proves the problem resolved.

## Smallest durable output boundary

`site/scripts/pagefind-build.ts` uses the existing engine's documented Node API:
create the index, add the same HTML directory, and obtain the complete bundle with
`getFiles()`. After those bytes arrive, close the native service. Node then owns all
writes, awaits each one and compares the resulting bytes with the in-memory bundle.
Every JavaScript asset is syntax-checked without execution, and entry metadata must
parse. Empty, duplicate, escaping or ambiguous output paths are rejected.

Files are assembled in a unique staging directory under the build output. The old
search output is replaced only after the entire staged bundle validates. An existing
symlink or non-directory is refused. Failures propagate; there are no sleeps,
rerun loops, waived tests, altered search results or ignored build errors.

The integration runs in `astro:build:done` for normal, direct and non-root Astro
builds. Starlight's default disk writer is explicitly disabled; the existing custom
search UI and content metadata remain. Pagefind 1.5.2 is declared directly as a
build dependency, matching the already-resolved lock entry. No dependency version,
integrity or transitive package node changes.

API authority: <https://pagefind.app/docs/node-api/>. The selected API and engine
version were also inspected in the exact installed lock-derived package, not
inferred from a different release.

## Verification and limits

Twenty unit/integration tests cover complete byte preservation, the observed
32-KiB truncation shape, syntax-check-without-execution, confined paths, duplicate
and empty assets, bad metadata, symlink refusal, failed service phases, service
shutdown before local writes and a real index built from a temporary HTML page.
The corrupted-module regression confirms rejection before replacing a previous
complete output; the main failure is not hidden behind a mocked provider.

A new hosted-browser check compares the served module with built bytes, imports its
actual exports and performs a real query. Its evidence records commit, tree, browser,
module size and digest. All existing search, workflow-navigation, storage, mobile
and visual tests remain enabled. Final exact-head browser and aggregate results
belong in the PR evidence comment, not a predeclared passing status in this file.

The diagnostic workflow's first build attempt correctly refused a checkout/run-SHA
mismatch. Its source and locked dependencies were recovered, but that failed
preparation build is not being represented as successful output evidence. Local
Chromium navigation was blocked by administrator policy; no policy bypass was
attempted. Hosted Chrome is the actual browser verification boundary.

Rollback the build integration, direct dependency declarations and their tests as
one unit; restore the default Starlight indexer explicitly. Do not remove the real
search acceptance checks to make a reverted build pass. No runtime governance,
Academy contract, release identity, policy or parent-branch change is included.
