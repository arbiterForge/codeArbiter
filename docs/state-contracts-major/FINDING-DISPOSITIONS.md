# Findings and verified-disposition worklist

The 70 original audit records include defects, source contradictions and intentional boundaries. They are not 70 interchangeable runtime bugs. Every record is mapped; no correction is marked implemented by this handoff.

| Record | Finding | Treatment | Tasks | Decisions |
|---|---|---|---|---|
| W-F01 | Conflict command prescribes a broader stop than the assistive engine contract | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-06, HW-27 | D-CONFLICT |
| W-F02 | Debug handoff treats a correctable packet error as a terminal one-shot boundary | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-07, HW-08, HW-27 | D-RESUBMIT |
| W-F03 | Maintenance severity and reviewer disposition conflict | DECISION_THEN_CHANGE | HW-09, HW-20, HW-27 | D-HIGH |
| W-F04 | Terminal finding harvest has no implemented recovery for interruption before the terminal step | IMPLEMENT_AUTHORIZED_CAPABILITY | HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-27 | D-RECOVERY |
| W-F05 | SessionStart persona documentation contradicts the prompt-submit owner | CLARIFY_CONTRACT_AND_VERIFY | HW-16, HW-27 |  |
| W-F06 | Sensitive-lines-only override wording understates the implemented candidate binding | CLARIFY_CONTRACT_AND_VERIFY | HW-17, HW-27 |  |
| W-F07 | Watch confuses absence of agent polling with absence of CLI polling | CLARIFY_CONTRACT_AND_VERIFY | HW-18, HW-27 |  |
| W-F08 | Command catalog and reviewer index drift from their owner bodies | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-19, HW-20, HW-27 |  |
| W-F09 | Compatibility-removal metadata encodes a different policy than the public owner | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-21, HW-27 |  |
| N-F01 | Ordinary context previews poison strict snapshot output recognition | CHANGE_WITH_PRESERVED_BOUNDARIES | NT-02 |  |
| N-F02 | Implemented repair-apply absent from capability operation list | CHANGE_WITH_PRESERVED_BOUNDARIES | NT-03 |  |
| N-F03 | Ordinary reconciliation and blocking propagate different task-state invalidation | DECISION_THEN_CHANGE | NT-09 | D-PROGRESS |
| N-F04 | Two kinds of review completion share REVIEW and accept-scope dispatch | DECISION_THEN_CHANGE | NT-09 | D-PROGRESS |
| N-F05 | Read-side effects depend on operation mode and platform | CLARIFY_CONTRACT_AND_VERIFY | NT-06 |  |
| N-F06 | Stored check-status vocabulary exceeds reachable public mutation behavior | CLARIFY_CONTRACT_AND_VERIFY | NT-07 |  |
| N-F07 | Task context does inspect scoped source for recorded checks | CLARIFY_CONTRACT_AND_VERIFY | NT-06 |  |
| N-F08 | Unsupported-platform message still describes Windows/macOS as pending | CLARIFY_CONTRACT_AND_VERIFY | NT-08 |  |
| N-F09 | Valid npm launch bindings exceed native completion consumer cap | CHANGE_WITH_PRESERVED_BOUNDARIES | NT-04 |  |
| N-F10 | Retirement with retained task checks or scope baselines is rejected as orphan state | CHANGE_WITH_PRESERVED_BOUNDARIES | NT-05 |  |
| HOOK-F01 | Returning to an already delivered mode suppresses the current persona | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-01, HW-27 |  |
| HOOK-F02 | Mode flip failure reports no change after raw state has already changed | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-02, HW-27 |  |
| HOOK-F03 | Pi doctor rejects the actual scoped package identity | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-03, HW-27 |  |
| HOOK-F04 | Qualified npm workspace binding can exceed native completion consumer limit | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-04, HW-27 |  |
| HOOK-F05 | Spinner uninstall restores backup over a user change made after install | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-05, HW-27 |  |
| HOOK-B01 | Debug validator rejection is stateless and does not prove authorization denial | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-07, HW-08, HW-27 | D-RESUBMIT |
| HOOK-B02 | Per-turn prompt owns persona delivery; SessionStart owns startup side effects | CLARIFY_CONTRACT_AND_VERIFY | HW-16, HW-27 |  |
| HOOK-B03 | Security review marker binds the complete staged candidate, not just sensitive lines | CLARIFY_CONTRACT_AND_VERIFY | HW-17, HW-27 |  |
| HOOK-B04 | No startup or knowledge backstop scans stranded terminal harvest residue | IMPLEMENT_AUTHORIZED_CAPABILITY | HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-27 | D-RECOVERY |
| HOOK-B05 | Native client accepts optional context qualification field | PRESERVE_AND_VERIFY_INTEROPERABILITY | HW-25, HW-27 |  |
| SF01 | Pi author child has no usable mutation authorization path | IMPLEMENT_AUTHORIZED_CAPABILITY | PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-D07 | D-PI |
| SF02 | Pi ready state can outlive failed persona initialization | CHANGE_WITH_PRESERVED_BOUNDARIES | PI-L01 |  |
| SF03 | Sidebar installs after disposal when metrics promise resolves late | CHANGE_WITH_PRESERVED_BOUNDARIES | PI-L02 |  |
| SF04 | Qualified production artifact manifests are rejected by farm parser | CHANGE_WITH_PRESERVED_BOUNDARIES | DIST-M01 |  |
| SF05 | Farm receipt failure is not a safe author-redispatch instruction | CHANGE_WITH_PRESERVED_BOUNDARIES | FARM-R01 |  |
| SF06 | Farm gate retry loses containment failure | CHANGE_WITH_PRESERVED_BOUNDARIES | FARM-R02 |  |
| SF07 | Farm Git observation failure can appear as no drift | CHANGE_WITH_PRESERVED_BOUNDARIES | FARM-R03 |  |
| SF08 | Sandbox dependency cache identity is tied to random checkout basename | CHANGE_WITH_PRESERVED_BOUNDARIES | SBX-C01 |  |
| SF09 | Sandbox output overflow kills observation client without stopping workload | CHANGE_WITH_PRESERVED_BOUNDARIES | SBX-C02 |  |
| SF10 | Sandbox cleanup and discovery sometimes claim more than observed | CHANGE_WITH_PRESERVED_BOUNDARIES | SBX-C03 |  |
| SF11 | Site search handles loader failure but not query/result-data failure | CHANGE_WITH_PRESERVED_BOUNDARIES | SITE-U01 |  |
| SF12 | Private Pi artifact prompt is not general installed Pi approval support | CHANGE_WITH_PRESERVED_BOUNDARIES | PI-D06, PI-C01 |  |
| SF13 | Surface and release build helpers have recoverable partial-write states | CHANGE_WITH_PRESERVED_BOUNDARIES | BUILD-G01 |  |
| SF14 | Compatibility metadata validates a removal slogan, not release-history authorization | CHANGE_WITH_PRESERVED_BOUNDARIES | BUILD-G02 |  |
| SF15 | Claude and Codex promotion intentionally differ but share unknown-outcome recovery | CHANGE_WITH_PRESERVED_BOUNDARIES | DIST-M02 |  |
| SF16 | Site drawer reconnect cleanup may duplicate local handlers | CHANGE_WITH_PRESERVED_BOUNDARIES | SITE-U02 |  |
| C-F01 | A public Release missing its final receipt cannot enter the advertised rerun recovery path | CHANGE_WITH_PRESERVED_BOUNDARIES | R-01 |  |
| C-F02 | Manual release description promises current main while source selection chooses latest successful main CI | CHANGE_WITH_PRESERVED_BOUNDARIES | R-02 |  |
| C-F03 | Release-skill pre-tag proof is effectively a required gate despite ADR 40 retaining it as advisory | DECISION_THEN_CHANGE | R-03 | D-GOV-PRETAG |
| C-F04 | Route compatibility publication clock has an implementation but no current release-workflow observation call | CHANGE_WITH_PRESERVED_BOUNDARIES | R-04 |  |
| C-F05 | Dedicated docs voice gate does not select PRs changing only its two rule implementation files | CHANGE_WITH_PRESERVED_BOUNDARIES | R-05 |  |
| C-F06 | A successful exit sometimes means unavailable or optional skip, not verified protection/runtime | CHANGE_WITH_PRESERVED_BOUNDARIES | R-06 |  |
| C-F07 | Payload first-introduction classification conflates absent base manifest and invalid base version | CHANGE_WITH_PRESERVED_BOUNDARIES | R-06 |  |
| C-F08 | Two verification subprocess paths lack a bounded wait before their normal timeout path | CHANGE_WITH_PRESERVED_BOUNDARIES | R-07 |  |
| SX-F01 | Documentation derives published-release state from tag presence alone | CHANGE_WITH_PRESERVED_BOUNDARIES | R-08 |  |
| T-F01 | Statusline benchmark comparison can print PASS for zero measurements | CHANGE_WITH_PRESERVED_BOUNDARIES | T-01 |  |
| T-F02 | Live SMARTS exercise tests literal lens-name presence rather than its stated material-comparison contract | CHANGE_WITH_PRESERVED_BOUNDARIES | T-01 |  |
| T-F03 | CI20 evidence binds HEAD and current workflow hash without ensuring workflow bytes belong to that HEAD | CHANGE_WITH_PRESERVED_BOUNDARIES | T-01 |  |
| T-F04 | Statusline illustration can proceed after failed renders and leaves some temporary inputs behind | CHANGE_WITH_PRESERVED_BOUNDARIES | T-01 |  |
| GEN-F01 | Prune nudge threshold describes total context instead of freed context | CLARIFY_CONTRACT_AND_VERIFY | HW-22, HW-27 |  |
| GEN-F02 | Hook reference is a bounded static extraction, not all actual runtime message text | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-23, HW-27 |  |
| GEN-B01 | Slug suffix counts do not reserve all output slugs | CHANGE_WITH_PRESERVED_BOUNDARIES | HW-24, HW-27 |  |
| SW-F01 | Sandbox preflight instructions refuse a dependency configuration that README and driver support | CLARIFY_CONTRACT_AND_VERIFY | SBX-D01 |  |
| SW-F02 | The same shell exit means persistent box in one owner and teardown in another | CLARIFY_CONTRACT_AND_VERIFY | SBX-D02 |  |
| SW-F03 | Single-box destroy prose drifts into a global prune and global-empty postcondition | CLARIFY_CONTRACT_AND_VERIFY | SBX-D02 |  |
| SW-F04 | Sandbox docs omit the temporary host copy of cloned source | CLARIFY_CONTRACT_AND_VERIFY | SBX-D03 |  |
| SW-F05 | Ordinary sandbox allowlist selection is described as applied although its run path stays offline | CLARIFY_CONTRACT_AND_VERIFY | SBX-D03 |  |
| SW-F06 | Cache reuse promise is repeated across independent sandbox surfaces | CHANGE_WITH_PRESERVED_BOUNDARIES | SBX-C01 |  |
| SW-F07 | Claude-inside requires codeArbiter maintainer evidence under the consumer project root | CHANGE_WITH_PRESERVED_BOUNDARIES | SBX-D04 |  |
| SW-F08 | Separate executable placement does not enforce five Claude-inside workflow phases | CLARIFY_CONTRACT_AND_VERIFY | SBX-D04 |  |
| SW-F09 | Claude README overstates dormant behavior and confines repository writes too narrowly | CLARIFY_CONTRACT_AND_VERIFY | HOST-D01 |  |

Source references, original finding text and diagnosis evidence are in the unchanged audit JSON and the structured disposition records. The implementation task ledger carries the full proposed correction and its acceptance/rollback requirements.
