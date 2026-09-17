# Design reference: HTML specifications and implementation plans

These schema-0.2.0 documents preserve the reviewed feature requirements: 26 acceptance criteria, 24 implementation tasks and six checkpoints. Both remain drafts with no implementation acceptance. They are re-rendered reference editions, not byte-identical historical archives. The packaged file identities are recorded in the adjacent `ORIGINAL-CONTRACT.json`.

The runtime engine uses a separate schema. Review its deviations explicitly; do not replace these behavioral requirements with the implementation schema or treat generated examples as acceptance evidence.

## Reference-only checks

Run `python tools/inspect_artifacts.py verify .` from this directory to check the pair. `python tools/run_review_tests.py --report /tmp/reference-tests.json` exercises reference regressions. Both use the local schemas; no network download occurs. Schema validation requires the Python packages listed in `requirements-review.txt` in the caller's environment. The optional browser check also requires Playwright and a local Chromium. These are review-tool dependencies, not production hook dependencies.

`review-report.md` records the design review rationale. Fresh reference validator and browser results describe only the included documents, not the Go engine or live host integration. Keep the HTML pair together for companion links.
