# Design-reference validation

These fresh results validate the schema-0.2.0 design review editions and their Python reference utilities. They do not confer approval on the implementation or its host integration.

| Check | Result |
|---|---|
| Reference tests | 41 passed; no failures, errors or skipped tests. |
| Schema, identities, digests and deterministic rendered views | Both documents passed. |
| Targeted criterion coverage | 26 of 26 criteria. |
| Plan structure | 24 tasks in six ordered checkpoint scopes; dependency graph acyclic. |
| Internal and companion links | 880 resolved. |
| Chromium layout | Four cells: both documents at 390/1440 pixels, including enlarged text and print-disclosure checks. |
| Authority | Drafts; no implementation tasks accepted; reference tools do not verify external approval. |

`review-tests.json` lists named outcomes. `browser-report.json` binds the current tested HTML bytes. `validation-report.json` records pair integrity and relationship results. Browser checks rendered exact bytes in memory with page JavaScript disabled; they are not native file-opening, complete accessibility, or cross-browser certification.

`review-report.md` retains the earlier design-review rationale, and `original-regression-reproduction.json` is historical reference-reader evidence. Current engine and integration evidence is separate under the merge package's `reports/current/` directory. The current implementation status, not this reference report, identifies unfinished runtime work.
