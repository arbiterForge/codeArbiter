import json
from pathlib import Path
import build_workflows as w

ROOT=w.ROOT
REPO=ROOT/'codeArbiter'
P='.github/scripts/check_codex_skill_resources.py'

def C(id,name,symbols,rows):
    w.M(id,name,[],rows,storage='Ephemeral collector process, isolated temporary profile, exact candidate bytes, explicitly supplied durable receipts',kind='implemented')
    m=w.machines[-1]
    m['sources']=[{'path':P,'symbol':symbols}]
    m['state_notation']='Analytical phases over actual branches, subprocesses and evidence; literal verdicts and durable evidence states are identified in the rows.'
    for t in m['transitions']: t['source']=m['sources']

C('CC-01','Codex fixture and durable characterization evidence',
  '_validate_matrix, _receipt_errors, validate_durable_artifacts, validate_fixture, validate_durable_record, main',[
('Unselected checker mode','Parse invocation','Exactly one fixtures-only/live/candidate-contract-only and compatible switches','Selected checker lane','Reject invalid invocation through argparse before live activity.','A valid offline fixture is not a live host qualification.'),
('Fixture bytes','Validate matrix and resources','Exact declared cells, nonces, resource links, release provenance and hashes','Valid fixture / invalid fixture','Hash fixture and evidence contract; collect explicit errors.','Required CLI/app-server cells are pinned to 0.143.0 and 0.145.0; advisory 0.149.0 is a separate class in this source snapshot.'),
('No durable record','Inspect receipt/report presence','Neither durable report nor receipt directory exists','pending','Report absence without manufacturing successful backend evidence.','An offline PASS can coexist with pending durable evidence.'),
('Durable record present','Validate report and all required receipts','Exact membership, paths, duplicate-free JSON, hash binding, successful supported cells and observed policies','complete / invalid','Accept complete only if all required evidence is mutually consistent; otherwise preserve errors.','A partial report/receipt set cannot silently regress to pending or count advisory as required proof.'),
('Receipt claims host support','Evaluate actual scope','Desktop-shell-proven must remain false in this contract','Backend-only evidence','Keep CLI/app-server result distinct from desktop shell behavior.','No hook-firing or desktop compatibility conclusion follows from these resource-read receipts alone.')])

C('CC-02','Isolated live resource probe and receipt classification',
  'validated_authenticated_codex_home, run_cli_live, run_app_server_live, build_live_receipt, _add_receipt_errors, main',[
('Live probe requested','Resolve exact binary and declared cell','Pinned supported cell or explicitly advisory cell; binary is a regular file','Preflight','Resolve executable and fixture/contract hashes; create temporary isolated profile.','latest means this checker’s captured advisory release, not an unbounded current-version lookup.'),
('Preflight','Compare executable digest','Actual hash equals declared native executable hash','Eligible probe / FAIL receipt','Hash mismatch returns failure before launching the candidate.','No inferred provenance from a requested version label.'),
('Eligible probe','Use authenticated temporary home','If supplied: exact controller-owned temp naming/containment and successful ChatGPT login status','Authenticated isolated probe / FAIL receipt','Build environment allowlist and separate profile/cache directories; inspect login without persisting raw output.','A supplied path outside the required cell root is rejected. A probe without supplied authentication does not become durable supported evidence merely by omitting the field.'),
('Eligible probe','Version and native install commands','Exact binary invoked; actual returned version and installation results checked','Installed / harness errors retained','Install local fixture marketplace and plugin through host commands; compare installed bytes under isolated plugin root.','Version/install errors accumulate; some later steps still run to produce evidence rather than turning a failed preflight into success.'),
('CLI plugin installed','Execute selected skill','read-only sandbox, never approval, disabled web search, exact entry and two linked resources','Observed CLI result','Run ephemeral structured-output turn; collect completed command events, paths and nonces.','Each subprocess has a timeout; CLI TimeoutExpired/OSError is not universally converted into a receipt by this path.'),
('Observed CLI result','Validate invocation and reads','Exactly one valid host invocation or one verified direct entry read; exactly three allowed successful direct reads','PASS / FAIL receipt','Bind actual executable, installed bytes, fixture, policy and sanitized canonical evidence hashes.','Agent-reported paths/nonces alone are insufficient; fallback searches or mismatched command events fail.'),
('Any observed result','Untrusted/secret-like content detected','Secret checks or unsafe error text','FAIL with redacted evidence','Replace persisted error text with constant classification and clear unsafe evidence hashes.','Raw streams are not copied into the receipt; failure-classification hashes are not successful transcript evidence.'),
('Receipt complete','Return process result','Supported versus advisory invocation','Exit0 / Exit1','Supported PASS exits0, supported FAIL exits1; advisory returns0 even with FAIL.','Exit0 alone therefore does not prove qualification; consumers must read verdict and evidence_class.'),
('Probe exits','Temporary scope ends','TemporaryDirectory cleanup','Ephemeral profile removed','Remove generated temporary marketplace/profile.','A separately supplied controller-owned authenticated home is not owned by TemporaryDirectory cleanup.')])

C('CC-03','App-server JSONL protocol and shutdown',
  '_JsonlClient, run_app_server_live, _agent_observation',[
('Process absent','Start app-server --stdio','Exact executable and isolated environment selected','Process running','Launch process; start stdout queue and stderr reader threads.','Streams/message lists are retained in memory; per-read timeout is not a total session deadline or global output cap.'),
('Process running','initialize response','Matching request id, object result and correct codexHome','Initialized','Send initialized notification, then skills/list with forceReload.','Error response, malformed JSON, EOF or missing response raises a protocol failure.'),
('Initialized','skills/list result','Exactly one namespaced selected skill, absolute installed path and matching bytes','Skill selected','Bind selected skill and installed root.','Missing, duplicate or relative skill selection cannot advance as successful proof.'),
('Skill selected','thread/start response','Thread id and actual effective readOnly sandbox with networkAccess=false','Thread established / errors retained','Request never approval and ephemeral thread; retain observed effective policies.','Requested policy does not replace the returned effective policy.'),
('Thread established','turn/start then notifications','Explicit skill input plus constrained read instructions','Await turn completion','Collect notification stream until turn/completed; record completed command events.','Every _next wait is bounded20seconds; continuous notifications can extend the overall operation.'),
('Await turn completion','turn/completed','Completed status and valid final agent JSON plus successful exact command evidence','Receipt validation','Inject host-observed requested/effective policy into observation and validate through common receipt builder.','Non-completed status or protocol failure yields errors; the last textual claim is not sufficient.'),
('Any launched process','finally close','Regardless of probe success','Closed / cleanup exception','Close stdin, wait2seconds, terminate then kill on successive timeouts, join reader threads and close streams.','This is bounded staged shutdown of the direct process; it is not a claim of arbitrary descendant-process containment.')])

C('CC-04','Candidate package snapshot and resource closure',
  '_candidate_package_files, _verified_large_candidate_files, candidate_resource_contract, validate_context_consumer_resources, candidate_static_contract',[
('Candidate argument','Inspect archive or directory','Regular non-symlink/reparse root and supported shape','Bounded enumeration','Reject unsafe entries, encrypted ZIP members, invalid modes, path escapes, normalized collisions and expansion limits.','Validation does not install or execute candidate bytes.'),
('Directory enumeration','Read entry','Same device/inode as enumerated regular file; size within declared bounds','Immutable in-memory snapshot / rejection','Read bounded bytes and reject changes beyond declared size; verify permitted promoted large binaries against receipt hashes.','Large-file exception is narrow and receipt-bound, not a general bypass of candidate bounds.'),
('Candidate snapshot','Detect context consumers','Any selected helper/consumer marker activates the whole required local set','Closed context set / rejection','Require named helper/consumer resources and expected contract entry markers.','Marker presence is static packaging evidence, not proof that runtime delivery succeeds.'),
('Candidate snapshot','Parse Markdown resources and links','UTF8 and supported link grammar; contained resolvable local Markdown links or named templates','Closed resource graph / rejection','Record selected file hashes and relative-read edges in deterministic order.','Remote links are not fetched; approved symbolic template destinations are not mistaken for concrete existing files.'),
('Candidate snapshot','Validate package identity/front matter/hooks','ca-codex identity, valid version, names match paths, exact approved hook manifest digest and present targets','Static package PASS / FAIL','Produce package/resource digests and selected paths.','An approved hook inventory digest proves the static contract only, not host hook invocation.'),
('Candidate static result','Return CLI','Complete inert validation result','Exit0 PASS / Exit1 FAIL','Print structured or human result.','No live authenticated turn or publication is implied by this lane.')])

C('CC-05','Constrained Markdown link parser context',
  '_mask_markdown_literal_regions, _inline_markdown_links, _markdown_resource_links, _candidate_front_matter',[
('Visible prose','Open fenced/quoted/list/indented code or HTML literal','Recognized grammar and current fence/indent state','Masked literal region','Blank literal characters while preserving offsets/newlines; retain specially recognized symbolic destination segments.','A filename match inside code or an HTML literal is not automatically a resource edge.'),
('Masked literal region','Matching close or indentation/context termination','Matching fence character/length, quote/list continuation rules','Visible prose','Resume link interpretation outside literal regions.','Unmatched literal delimiters retain their actual parser behavior; not a general CommonMark library guarantee.'),
('Visible prose','Inline backticks or escaped/image syntax','Matched delimiter or recognized literal form','Masked span / visible prose','Ignore code spans, escaped references and image-like regions for resource links.','An unmatched code span is left visible by this scanner.'),
('Visible prose','Inline link label/destination','Balanced labels, parentheses depth<=32 and supported optional title','Resolved target / parser rejection','Unescape supported punctuation and return target with occupied span.','Malformed/unsupported/unterminated destination or title raises explicit ValueError.'),
('Visible prose','Reference definition and use','Unique normalized label; existing definition for full/collapsed reference','Resolved target / parser rejection','Resolve supported full/collapsed/defined shortcut references outside occupied spans.','Duplicate or unresolved reference-style definitions fail instead of guessing a target.'),
('Resource beginning','Scalar front matter','Opening/closing delimiter, unique allowed key grammar and required nonempty fields','Front matter accepted / rejection','Decode supported quoted scalar values and verify name/path relation in package owner.','Multiline/unsupported front matter is rejected by this deliberately constrained parser, not silently interpreted as YAML.')])

def F(id,title,detail,paths,decision,severity='medium',status='source-confirmed documentation or policy contradiction'):
    return {'id':id,'severity':severity,'status':status,'title':title,'detail':detail,
            'sources':[{'path':p,'symbol':'Full source read'} for p in paths],
            'recommendation':decision}

findings=[
F('W-F01','Conflict command prescribes a broader stop than the assistive engine contract',
  'The conflict command says all work stops when governing rules conflict. Current sprint/context guidance and ADR0043 describe refusal scoped to dependent work. These cannot both be a universal rule. Source does not implement a single dependency-aware conflict controller.',
  ['core/surface/commands/conflict.md','core/surface/SPRINT.md','core/surface/skills/context-check/SKILL.md','.codearbiter/decisions/0043-assistive-state-engine.md'],
  'Choose and document the stop scope explicitly. Recommend stop affected authority/data dependencies, preserve independent read-only work, and keep genuine global host/user stops global. This is a policy decision, not a silent prose cleanup.'),
F('W-F02','Debug handoff treats a correctable packet error as a terminal one-shot boundary',
  'The workflow forbids repairing and resubmitting any rejected packet. The validator is stateless and distinguishes malformed/invalid packets from internal I/O errors; it records no consumed one-shot capability. The prose therefore imposes an extra recovery policy beyond implementation.',
  ['core/surface/skills/debug/SKILL.md','core/pysrc/_debughandofflib.py','core/pysrc/debug-handoff.py'],
  'Separate invalid input, denied authority, stale binding and internal failure. Permit an explicitly corrected new input attempt where authority remains valid; retain the refusal for an unchanged denied request. Requires approved workflow-policy change.'),
F('W-F03','Maintenance severity and reviewer disposition conflict',
  'The dependency reviewer can report HIGH maintenance risk while saying not to block on maintenance alone. The included reviewer contract says every HIGH is blocking and additions never replace that rule. This makes a correct verdict ambiguous for the reviewing agent and user.',
  ['core/surface/agents/dependency-reviewer.md','core/surface/includes/reviewer-contract.md'],
  'Represent severity and disposition separately; document the explicit maintenance-only disposition exception or revise its severity. Generate the common verdict contract from the selected policy.'),
F('W-F04','Terminal finding harvest has no implemented recovery for interruption before the terminal step',
  'Several workflows harvest qualifying findings at completion. The knowledge helper and session/standup paths do not implement a durable pending-harvest backstop. An interrupted run can therefore leave eligible findings only in conversation; the source does not prove every such finding is lost.',
  ['core/surface/includes/harvest.md','core/surface/includes/knowledge.md','core/pysrc/_knowledgelib.py','core/pysrc/session-start.py','core/surface/commands/standup.md'],
  'Keep harvest opportunistic. If durable recovery is desired, record bounded pending candidates at discovery and settle/deduplicate on completion/resume. Register any new output with all native readers; do not introduce a new universal completion gate.',status='source-confirmed recovery gap'),
F('W-F05','SessionStart persona documentation contradicts the prompt-submit owner',
  'Init/porting language attributes persona injection to SessionStart. The implemented SessionStart path and ADR0030 place full composed persona delivery in UserPromptSubmit; a mode revisitation bug is documented separately in the hooks findings.',
  ['core/surface/commands/init.md','README.md','core/pysrc/session-start.py','core/pysrc/prompt-submit.py','.codearbiter/decisions/0030-orchestration-mode-plane-with-composed-persona.md'],
  'Make prompt-submit the documented delivery owner and distinguish session setup, selected mode, committed mode and delivered persona.'),
F('W-F06','Sensitive-lines-only override wording understates the implemented candidate binding',
  'The override surface describes an invalidation scope around sensitive lines. The security pass and binding helper retain full candidate/worktree/sensitive digests and hash the complete staged UTF8 diff. A user cannot reliably predict grant reuse from the narrower wording.',
  ['core/surface/commands/override.md','core/pysrc/security-pass.py','core/pysrc/_sensitivelib.py'],
  'Document the exact binding tuple and invalidation event. Preserve current security semantics while deriving override help from the same binding definition.'),
F('W-F07','Watch confuses absence of agent polling with absence of CLI polling',
  'The watch command describes gh pr checks --watch as server-side blocking with no polling interval. The official gh command documents --interval with default10seconds. Waiting in one detached CLI invocation avoids model-driven polling, but the underlying CLI still refreshes periodically.',
  ['core/surface/commands/watch.md'],
  'Say one detached gh watch process with no repeated agent calls; preserve its timeout/cancel behavior. Correct the no-polling claim.',severity='low'),
F('W-F08','Command catalog and reviewer index drift from their owner bodies',
  'COMMANDS.md calls Tribunal eleven-lens while the current owner/reference set contains thirteen. Its release signature uses --dry-run and SemVer-only language where the current owner uses --dryrun and supports numeric sequence targets. The agent index also presents coverage behavior more strongly than the coverage reviewer body does.',
  ['core/surface/COMMANDS.md','core/surface/commands/tribunal.md','core/surface/skills/tribunal/SKILL.md','core/surface/commands/release.md','core/surface/agents/INDEX.md','core/surface/agents/coverage-auditor.md'],
  'Generate signatures, lens count and index descriptions from explicit owner metadata; do not change actual command spelling or verdict rules just to match stale summaries.',severity='low'),
F('W-F09','Compatibility-removal metadata encodes a different policy than the public owner',
  'command-routes.json removalRequires is minor-release-with-changelog-notice. build-surface.py enforces that literal vocabulary. The command compatibility policy describes a major/1.0 floor plus a separate approved removal decision and fresh evidence. The release-state observer does not enforce removalRequires. This is a dormant metadata/policy conflict, not proof of an unauthorized live alias removal.',
  ['core/surface/command-routes.json','tools/build-surface.py','core/surface/includes/command-compatibility.md','.github/scripts/check_command_route_release_state.py'],
  'Choose the approved retirement rule, give it one owner and generate both policy prose and accepted registry values. Preserve existing aliases until the separately approved removal conditions are met.'),
]

# Make incorrect inferred paths impossible to carry into the finished audit.
for m in w.machines:
    for s in m['sources']:
        if not (REPO/s['path']).is_file(): raise ValueError(s['path'])
for f in findings:
    for s in f['sources']:
        if not (REPO/s['path']).is_file(): raise ValueError(s['path'])

w.write()
out=json.loads((ROOT/'audit-work/workflows.json').read_text())
out['findings']=findings
out['scope']='Model-guided canonical installed workflows; statusline/usage owner code; Codex resource characterization and candidate parser'
(ROOT/'audit-work/workflows.json').write_text(json.dumps(out,indent=2)+'\n')

paths=sorted(str(p.relative_to(REPO)) for p in (REPO/'core/surface').rglob('*.md'))
paths+=['README.md','core/surface/COMMANDS.md','core/surface/SPRINT.md','core/surface/arbiter.md','core/surface/command-routes.json',P]
paths+=['core/pysrc/'+p for p in ['statusline.py','_segmentslib.py','_usagelib.py','_colorlib.py','_boxlib.py','_fmtlib.py']]
paths+=['.codearbiter/decisions/'+p for p in ['0030-orchestration-mode-plane-with-composed-persona.md','0036-bounded-authorization-cleanup-direction.md','0037-extensible-structured-artifact-engine.md','0043-assistive-state-engine.md']]
coverage={'commit':w.SHA,'method':'Full files read in bounded chunks. Core workflow Markdown includes complete owner bodies and linked local reference/lens files. Runtime comments were treated as claims and compared with branches. ADR status is not implementation proof.',
          'files':[{'path':p,'read':'full','lines':len((REPO/p).read_text().splitlines())} for p in sorted(set(paths))],
          'additional_targeted_reads':'Selected native and hook source branches, registry metadata, source probes and historical Project Sources; those are not counted as additional full-file reads.'}
(ROOT/'audit-work/root-read-files.json').write_text(json.dumps(coverage,indent=2)+'\n')
print(json.dumps({'machines':len(w.machines),'transitions':sum(len(m['transitions']) for m in w.machines),'findings':len(findings),'root_full_files':len(coverage['files'])}))
