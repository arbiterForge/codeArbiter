import { REVIEWED_AT, type AtlasView, type AtlasNode, type AtlasEdge, type AtlasKind, type AtlasRelation } from './atlas-model';
const source = (path: string, blob: string) => ({ path, blob, revision: REVIEWED_AT });
export const atlasSources = {
  review: source('core/surface/commands/review.md','bd2ebd5beb9470f6b9a19a4d6986772b51cf365e'),
  finish: source('core/surface/skills/finishing-a-development-branch/SKILL.md','848ef48bd509a43f677d69485e5e1914b09bd1b5'),
  artifacts: source('core/surface/includes/artifacts.md','1cd2463cffe4f2ab652a3a3c65582f067cffa632'),
  context: source('core/surface/skills/context-creation/SKILL.md','6c2471a0553729bd0e349580c08a72657e54f0ad'),
  debug: source('core/surface/skills/debug/SKILL.md','29b4f9541fa0969459fbbbabac7e528f24c795ce'),
  fix: source('core/surface/commands/fix.md','e5e8c44994c1c245b4461014dce30b3d4553daa7'),
  tribunal: source('core/surface/skills/tribunal/SKILL.md','fe1d538deac174300b9b24e28b8fb561fef37d96'),
};
const n = (id: string, kind: AtlasKind, title: string, detail: string, output: string, source: string): AtlasNode => ({id,kind,title,detail,output,source});
const e = (from: string,to: string,kind: AtlasRelation,label: string,detail: string,source: string): AtlasEdge => ({from,to,kind,label,detail,source});
export const supplementalViews: AtlasView[] = [
  {
    id:'context-layers',title:'How context reaches the person or agent doing the work',sources:atlasSources,
    boundary:'A source-linked explanation. Prepared context, delivered context, approval and verified results have different owners. The engine checks structure and identity, not semantic truth.',
    outcome:'A scoped input delivered to the actual actor, followed by the evidence required by its caller.',
    chapters:[
      {id:'select',title:'Select the governing inputs',nodes:[
        n('knowledge','context','Repository knowledge','Project context, stack, standards and applicable controls provide orientation. A code map is a search pointer; inspect current source before relying on it.','Scoped facts with sources and explicit gaps.','debug'),
        n('pair','state','Approved specification and plan','A qualified new full-lane pair uses typed HTML. Existing Markdown pairs remain legacy; a small feature uses an inline mini-spec. Missing capability stops typed authoring.','Current artifact identity and the obligations for this work.','artifacts'),
        n('scope','context','Task and caller scope','For a fix, include the actual task paths, symptom, expected behavior, reproduction limits, evidence and named regression test. Command declarations retain their working directory and observed verification state.','Bounded actor input that still requires the actor to check applicability.','fix'),
      ]},
      {id:'deliver',title:'Deliver to the actual actor',nodes:[
        n('packet','context','Compose the input','Compose the route-specific input from current constraints and host-effective instructions. Orientation never grants permission to execute a discovered command.','A selected input packet, not a proof receipt.','fix'),
        n('delivery','gate','Bind and deliver','Prepare actor delivery for the actual author, task, worktree and current epochs. Send the returned delivery text, retain the attempt and stop material action when blocked.','An actual delivery attempt bound to the intended actor.','fix'),
        n('refresh','context','Reselect when context changes','Resume, compaction or a changed scope requires reselection. A shared session marker cannot stand in for an author receipt.','Current inputs or a precise missing-context stop.','fix'),
      ]},
      {id:'evidence',title:'Return evidence without conflating it with context',nodes:[
        n('red','gate','Observe the target failure','The fix caller must observe the named regression test fail for the defect at the production layer. An import error, setup failure or unrelated red does not clear this gate.','Target-red evidence before fix code.','fix'),
        n('proof','output','Verify under the owning procedure','The current artifact route retains review, fresh verification and the applicable authority producers. A formatted document or a successful capability read is not a completed host workflow.','Source-bound evidence for the next owning gate.','artifacts'),
      ]},
    ],
    edges:[e('knowledge','packet','context','orientation','Select only relevant source-backed project knowledge.','fix'),e('pair','packet','context','obligations','Typed and legacy artifact routes retain distinct admission and approval rules.','artifacts'),e('scope','packet','context','bounded task','The input preserves the original caller and task scope.','fix'),e('packet','delivery','sequence','actual actor','Preparing a packet is not the same as delivering it.','fix'),e('delivery','red','conditional','authorized work','Delivery and the original repair authority are prerequisites; delivery itself grants no authority.','fix'),e('delivery','refresh','conditional','interrupted or changed','Re-establish applicable inputs rather than reusing a session marker.','fix'),e('refresh','packet','return','reselect','Compose again from current observations and epochs.','fix'),e('red','proof','sequence','minimal repair','Proceed through the remaining TDD and review gates after the correct failure.','fix')],
  },
  {
    id:'debug-fix',title:'Investigate a symptom and return to an authorized repair',sources:atlasSources,
    boundary:'Diagnosis is read-only. A handoff recommendation, its structural validity or a diagnosis-only request cannot authorize a patch.',
    outcome:'One of five diagnostic dispositions; only a current, supported code defect can continue through the original authorized fix caller.',
    chapters:[
      {id:'investigate',title:'Establish the claim and its evidence',nodes:[
        n('symptom','command','Debug or bounded fix prerequisite','Retain the symptom, available expectation, reproduction state, evidence identity and actual request scope. A direct confirmed fix need not re-enter debug.','An identifiable case with unknowns retained.','debug'),
        n('hypothesis','skill','Discriminate the hypotheses','Select distinct plausible mechanisms and real distinguishing observations. There is no quota of hypotheses and a recent change is not causal proof.','Evidence that confirms, narrows or refutes candidate mechanisms.','debug'),
        n('disposition','output','Name the diagnostic disposition','Return confirmed_code_defect, confirmed_non_code_cause, design_question, no_action or unresolved. Non-code, unresolved and no-action outcomes stop dependent repair.','Evidence, limits and the next owner or resume condition.','fix'),
      ]},
      {id:'admit',title:'A code-defect handoff has separate admission checks',nodes:[
        n('packet-check','gate','Validate an available packet','Use the trusted installed handoff validator. Accept only its successful valid result. There is no silent packet rewrite or unvalidated fallback.','Structurally valid handoff bytes, not verified truth.','fix'),
        n('authority','gate','Recheck source and authority','Compare actual worktree, source, runtime and dirty state against the cited evidence. The original caller must already authorize repair; the packet cannot grant it.','A current supported claim and original repair scope.','fix'),
        n('target-red','gate','Observe the named test red','Write or reuse the supported regression test. It must fail for the defect before fix code; unrelated failure or a passing test is insufficient.','Causal target-red evidence.','fix'),
        n('repair','output','Minimal repair and remaining TDD','Select the domain author, deliver current context and follow the remaining TDD gates. Commit and delivery retain their separate owners.','Verified fix work returned to its caller.','fix'),
      ]},
      {id:'other',title:'Other outcomes preserve their own boundaries',nodes:[
        n('design','output','Design question','Report the intended-behavior decision and stop dependent repair. An ADR is not created automatically.','A decision for its existing owner.','fix'),
        n('closed','output','Positive no-action closure','Return positive evidence supporting closure. The diagnostic result makes no default board write or state change.','A bounded no-action result.','fix'),
        n('unresolved','output','Non-code or unresolved','Return the responsible owner, evidence gap, blocker or condition needed to resume. A separately authorized task uses its own writer.','A bounded result rather than a forced code patch.','fix'),
      ]},
    ],
    edges:[e('symptom','hypothesis','sequence','investigate','Safe targeted investigation preserves scope and missing facts.','debug'),e('hypothesis','disposition','sequence','evidence','Select the supported disposition rather than forcing a code defect.','debug'),e('disposition','packet-check','conditional','code defect packet','Only a confirmed_code_defect packet targeting fix is eligible for this continuation.','fix'),e('packet-check','authority','sequence','independent checks','Structural success does not establish freshness or authorization.','fix'),e('authority','target-red','conditional','repair authorized','Diagnosis-only requests stop at their recommendation.','fix'),e('target-red','repair','sequence','correct failure','The same regression obligation drives the minimal fix.','fix'),e('disposition','design','conditional','design_question','A design discussion is not an automatic ADR.','fix'),e('disposition','closed','conditional','no_action','Positive closure evidence is required.','fix'),e('disposition','unresolved','conditional','other dispositions','Non-code and unresolved outcomes stop dependent repair.','fix')],
  },
  {
    id:'tribunal',title:'A source-bound audit ends only after its follow-ups',sources:atlasSources,
    boundary:'Deliberate opt-in audit, never a routine merge gate. The lens roster comes from the installed source cards. Finding scope, evidence scope and external-action authority remain separate.',
    outcome:'A source-bound report, supported work and recorded filing/telemetry dispositions before run-completed.',
    chapters:[
      {id:'bind',title:'Bind the source and acknowledge cost',nodes:[
        n('intent','command','Deliberate audit intent','Resolve finding scope, bounded evidence and the trusted review bundle. Candidate repository content cannot change the audit contract or authorize execution.','An audit request with explicit evidence boundaries.','tribunal'),
        n('resume','state','Inspect existing run state','Same-source audit resumes unfinished waves; follow-up resumes pending dispositions. Drift, legacy-unbound and invalid records cannot be reused as current progress.','A justified resume or a fresh run.','tribunal'),
        n('cost','gate','Acknowledge cost before dispatch','Use deterministic inventory and actual host profiles to estimate bounded packets. Show uncertainty, settings and independence limits before model dispatch.','Acknowledged cost and supported settings.','tribunal'),
        n('start','state','Bind a fresh run','Use the returned run ID and directory. Bind concrete source inputs before reviewers; adding outside evidence requires a new binding.','Durable source identity and selected audit scope.','tribunal'),
      ]},
      {id:'review',title:'Review the applicable lenses and persist findings',nodes:[
        n('inventory','context','Inventory and risk map','Keep mechanical inventory distinct from judgment about risk. Account for every lens with applicability or a skip rationale and bounded evidence.','Source-bound packets and explicit coverage limits.','tribunal'),
        n('review','agent','Generic lens reviewer','Dispatch MODE review per active lens within host capacity and at most five concurrent. Specialists do not dispatch children or edit shared logs.','Immediate finding and lead records.','tribunal'),
        n('verify','agent','Fresh serious-claim verification','Attempt MODE verify for every critical/high or expensive inferential claim. Record confirmed, narrowed, refuted or inconclusive and actual independence.','A disproof attempt with its observed limits.','tribunal'),
        n('triage','gate','Eligibility and root-cause triage','Only supported eligible keep/combine work enters plans. Unverified serious claims remain verify-required; genuine design forks remain separate.','Wave plans plus dispositions for every finding and lead.','tribunal'),
      ]},
      {id:'finish',title:'Report, then resolve both follow-ups',nodes:[
        n('report','output','Write the report','Project durable records into report and manifest, including refutations, unresolved work and coverage limits. report-written enters follow-up.','A report, not terminal completion.','tribunal'),
        n('filing','gate','Filing disposition','Deduplicate selected eligible findings. Execute filing only with explicit authorization; a chosen handoff records filing-skipped. Failures and unanswered choices remain pending.','issues-filed or explicit filing-skipped.','tribunal'),
        n('telemetry','gate','Optional public telemetry','Preview the aggregate and its public destination before per-run consent. Do not include source hashes, paths, code or finding text. No answer remains pending.','telemetry-sent or explicit telemetry-skipped.','tribunal'),
        n('complete','output','Record run-completed','Recheck source before follow-up actions. Complete only after both filing and telemetry dispositions. The audit does not repair, commit or merge code.','Terminal run-completed signal with history retained.','tribunal'),
      ]},
    ],
    edges:[e('intent','resume','sequence','inspect','Source identity, not elapsed age, governs reuse.','tribunal'),e('resume','cost','conditional','fresh work','Prepare a fresh binding when required.','tribunal'),e('cost','start','sequence','acknowledged','No model dispatch precedes cost acknowledgement.','tribunal'),e('start','inventory','sequence','bound source','Risk judgment uses represented evidence.','tribunal'),e('inventory','review','dispatch','applicable lenses','Record skipped lenses and the actual capacity bound.','tribunal'),e('review','verify','conditional','serious claims','Freshness alone does not establish independent verification.','tribunal'),e('verify','triage','return','observed outcome','Refuted and unverified serious claims cannot become confirmed repair work.','tribunal'),e('review','triage','conditional','other candidates','All candidates still face confidence and eligibility checks.','tribunal'),e('triage','report','sequence','waves accounted for','Account for every finding and lead before report projection.','tribunal'),e('report','filing','sequence','follow-up','A written report creates no issues.','tribunal'),e('filing','telemetry','sequence','separate choice','Filing consent does not authorize telemetry.','tribunal'),e('telemetry','complete','conditional','both resolved','Both dispositions must be done or explicitly skipped.','tribunal'),e('resume','inventory','conditional','unchanged audit','Continue unfinished recorded waves without inventing new progress.','tribunal'),e('resume','filing','conditional','unchanged follow-up','Continue only unresolved dispositions, preserving partial receipts.','tribunal')],
  },
  {
    id:'review-delivery',title:'Review, commit and branch disposition are different decisions',sources:atlasSources,
    boundary:'Read-only review returns a local verdict. Posting, committing, opening a PR, merging and discarding have separate authority. Watching and cleanup select their owners before creation preflight.',
    outcome:'The requested review or branch disposition, with the exact observed source and check state.',
    chapters:[
      {id:'review',title:'Read one diff and return one verdict',nodes:[
        n('diff','command','Resolve the requested diff','Use the current diff, a path or one fetched inbound PR diff. Reviewing an inbound PR does not check out its branch.','One consistent diff for the reviewer fleet.','review'),
        n('review-input','context','Deliver reviewer context','Select bounded current context per actual reviewer and preserve host instruction precedence. Ready is preflight, not delivery; an author receipt cannot substitute.','Actual reviewer input and delivery attempts.','review'),
        n('verdict','output','Triage into a local verdict','Path-selected reviewers return through finding-triage and the read-only verdict-aggregator. This is not a persisted checkpoint.','Findings with evidence and explicit gaps.','review'),
        n('post','gate','Post only when requested','An inbound review reports locally first. Posting a comment is separately confirmed and conveys neither approval nor request-changes authority.','A local verdict or an explicitly requested public comment.','review'),
      ]},
      {id:'finish',title:'Continue only into the requested delivery action',nodes:[
        n('commit','gate','Current-head commit gate','PR creation and terminal branch actions require the current-head commit gate. When an HTML pair exists, current native acceptance is rechecked.','Current evidence for the selected branch and artifacts.','finish'),
        n('pr','output','Open the requested PR','A direct open-PR request already selects that outcome. The finishing owner executes its PR procedure without re-invoking the public wrapper.','An open PR, its head and observed checks.','finish'),
        n('merge','gate','Merge is separate','Exact-head hosted evidence and the explicit merge decision still apply. A sprint ends at its PR and does not merge or discard.','The separately authorized branch disposition.','finish'),
      ]},
      {id:'alternatives',title:'Existing-PR operations select their own owners',nodes:[
        n('watch','command','Watch the existing PR','The watch mode resolves before PR-creation preflight and returns after its owner finishes. It does not open another PR.','Observed checks for the selected PR.','finish'),
        n('cleanup','command','Post-merge cleanup','The cleanup mode uses its own fetched-containment proof and per-item confirmations. It does not require new creation-time plan completion.','Only the individually confirmed cleanup actions.','finish'),
      ]},
    ],
    edges:[e('diff','review-input','sequence','one scope','Every reviewer must inspect the same resolved diff.','review'),e('review-input','verdict','dispatch','actual delivery','Missing critical input stops the substantive verdict, while bounded safe orientation may continue.','review'),e('verdict','post','conditional','public comment requested','The local result is the default output.','review'),e('verdict','commit','conditional','own change and authorized delivery','A review alone does not authorize mutation; blocking own-change findings require correction.','review'),e('commit','pr','conditional','open PR selected','Commit proof and the requested action remain separate.','finish'),e('pr','merge','conditional','merge authorized','Opening a PR is not a merge instruction.','finish')],
  },
];
