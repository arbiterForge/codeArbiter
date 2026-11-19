from pathlib import Path
import json

BASE = Path('/workspace/scratch/6dd9dc5f561f')
REPO = BASE / 'codeArbiter'
OUT = BASE / 'audit-work'
COMMIT = 'fd7eb34b2da439551443d09526ab48fd1d1bb9bf'
machines = []
findings = []

def T(frm, event, guard, to, effects, failure='', source=None):
    return dict(from_state=frm, event=event, guard=guard, to=to,
                effects=effects, failure_retry=failure, source=source)

def M(id, name, storage, states, sources, rows, kind='implemented', notes=''):
    parsed = []
    for source in sources:
        path, symbol, lines = source.split('|')
        p = REPO/path
        if p.exists() and lines.startswith('1-'):
            lines = f'1-{len(p.read_text().splitlines())}'
        parsed.append(dict(path=path, symbol=symbol, lines=lines))
    for row in rows:
        row['from'] = row.pop('from_state')
        if row['source'] is None:
            row['source'] = '; '.join(f'{s["path"]}:{s["symbol"]}:{s["lines"]}' for s in parsed)
    machines.append(dict(id=id, name=name, kind=kind, state_storage=storage,
                         states=states.split(';'), sources=parsed,
                         transitions=rows, notes=notes))

def F(id, title, evidence, implication, recommendation, confidence='source-confirmed', probes=None):
    findings.append(dict(id=id,title=title,evidence=evidence,implication=implication,
                         recommendation=recommendation,confidence=confidence,probes=probes or []))

PI='plugins/ca-pi/tools/src/'
SB='plugins/ca-sandbox/tools/'

M('S01','Pi session activation, ownership and degradation',
  'Closure fields enabled/persona/state; lifecycle sequence and current lease; independent bridge/command/ownership degradation flags; project activation marker.',
  'dormant;activation pending;waiting for trust;bootstrapping;ready;ready but degraded;invalidated;shut down',
  [PI+'extension.ts|codeArbiterExtension and session handlers|1-1130',PI+'activation.ts|activation ownership|1-81',PI+'session-identity.ts|session identity|1-33'],[
  T('any session','session_start','new lifecycle sequence','activation pending','Invalidate prior lease; stop background jobs for session switch; dispose sidebar/activity; deactivate wrappers; reset bridge/session state; create activity/lease; start footer; read activation marker.'),
  T('activation pending','activation marker absent/false','marker is readable and not enabled','dormant','Clear active lease and return after footer/sidebar setup; native Pi remains the owner.','Marker read errors are handled by activation path; no author mutation authority is granted.'),
  T('activation pending','enabled marker read','context untrusted','waiting for trust','Keep final mutation gate blocked and show waiting status.','Trust restoration requires an eligible new lifecycle; a stale lease cannot reactivate it.'),
  T('activation pending','enabled marker + trusted context','valid session lease','bootstrapping','Enable adapter; register plan/jobs; begin enforcement bootstrap; resolve command ownership; prepare bridge; install owned wrappers.'),
  T('bootstrapping','wrapper installation succeeds','same active lifecycle','ready','markReady; activate background controller; restore plan state; then load persona and call session-start bridge.'),
  T('bootstrapping','wrapper installation throws','installation attempted','invalidated','Invalidate lease, stop jobs with fatal reason, disable adapter, report error and throw.','Bridge preparation is before the installation try block; not all failures share the same recovery path.'),
  T('ready','persona read OR session-start bridge throws','readiness was already marked','ready but degraded','Catch marks bridge degradation and leaves enabled/ready true.','Persona load has no independent retry state. Later bridge refresh can clear degradation without restoring missing persona.'),
  T('ready or degraded','before_agent_start','current trusted lease','ready or degraded','Refresh bridge; append persona/state to prompt; apply notices; successful bridge read clears bridge degradation.','Stale lease suppresses result; bridge failure degrades, not automatic disable.'),
  T('ready or degraded','agent_start / agent_end / turn_end','current lifecycle','same lifecycle','Set governed/degraded status; refresh footer and sidebar with lifecycle guards.'),
  T('any active','shutdown/new/resume/fork/reload','event-specific reason','invalidated then shut down','Invalidate first; stop jobs; dispose UI; clear state; deactivate enforcement.','Outstanding UI work needs its own generation check; sidebar has a separate stale-install defect.')
  ],notes='Readiness, persona load, bridge health, trust, command ownership, plan mode and background health are independent axes, not one linear session status.')

M('S02','Pi final tool enforcement and permission transaction',
  'Tool-wrapper registry/generation; bootstrap active/ready flags; lifecycleGeneration; trust-revoked latch; frozen canonical parameters; current plan mode and lease.',
  'dormant;bootstrap blocked;ready;trust revoked;permission pending;approved audit pending;executing;blocked',
  [PI+'tool-guard.ts|createToolEnforcement, confirmationUi, wrapper execute|1-963',PI+'policy.ts|permission decision|1-319'],[
  T('dormant','native read or ordinary built-in call','adapter inactive','dormant','Delegate native built-ins; custom mutators without native fallback remain unavailable.'),
  T('any','beginActivation / beginBootstrap','new lifecycle','bootstrap blocked','Advance generation; install/read final gate; permit native read fallback; prevent mutators until ready.'),
  T('bootstrap blocked','markReady','current generation and trust not revoked','ready','Allow wrapped calls to reach authorization evaluation.'),
  T('ready','trust becomes false','observed at gate or revalidation','trust revoked','Latch revocation, clear readiness, advance generation, block mutation.','Trust becoming true alone does not revive old authority; require new lifecycle.'),
  T('ready','unknown OTHER tool invocation','no owned known mutator wrapper','blocked','Reject rather than allow an unclassified side-effecting sink.'),
  T('ready','known tool invocation','owned wrapper, live lease, bounded canonical params','ready','Freeze/canonicalize params; bridge hard-block decision first; then mode-specific permission policy.'),
  T('ready','bridge decision denies / policy denies / invalid params','any deny','blocked','Throw refusal; best-effort audit.','Read/lifecycle bridge failures may degrade elsewhere; mutator bridge failures refuse.'),
  T('ready','policy allows','e.g. native read, inspection, eligible plan edit','executing','Best-effort audit and execute through canonical owned native tool; generation/trust checks remain authoritative.'),
  T('ready','policy asks','execute-mode mutator','permission pending','Open confirmation only in trusted TUI with confirm API; 60-second bound.','RPC/no UI refuses immediately; dialog timeout/cancel/refusal audit best effort then block.'),
  T('permission pending','user approves','lease/trust/mode/generation/ownership/params unchanged and not aborted','approved audit pending','Require approved permission audit to succeed before any native mutation.','Audit failure blocks mutation even if user confirmed; user approval alone is insufficient.'),
  T('approved audit pending','audit persisted','all authority revalidated again','executing','Invoke exact native mutator once with frozen parameters.','No blind mutation retry on execute failure; caller receives tool error.'),
  T('permission pending or approved audit pending','abort or authority drift','any revalidation fails','blocked','Discard approval; never execute stale call.','Fresh invocation may request new approval under current authority.'),
  T('any','late tool_result','result generation differs','same state','Ignore stale final-result hook; do not credit current lifecycle.'),
  T('any','deactivate','lifecycle ending','dormant','Invalidate owned generation and restore supported native fallback behavior.')
  ])

M('S03','Pi plan mode and revision-controlled file editing',
  'Owned plan lease; session entry version/revision; mode/disposition; task states; current file hash; append-only session persistence.',
  'unowned execute;plan draft;plan edit pending;approved execute;cancelled execute;ownership lost',
  [PI+'plan-mode.ts|PlanModeController|1-546',PI+'native-plan.ts|native plan adapter|1-365'],[
  T('unowned execute','enter plan','trusted live lease; safe canonical path; valid tasks/hash','plan draft','Read plan, acquire ownership, persist revision 1 with mode=plan and disposition=draft.'),
  T('plan draft','edit task state','same expected hash; legal task move','plan edit pending','Permit PENDING→IN_PROGRESS/ACCEPTED; IN_PROGRESS→ACCEPTED; retain ACCEPTED; native edit is restricted to owned plan semantics.'),
  T('plan edit pending','file write + observation succeed','unchanged lease and task IDs','plan draft','Record new hash/revision and persisted state.'),
  T('plan edit pending','write committed but response/readback lost','commit may have happened','plan draft or unresolved edit','Return ok=false with committed=true; re-observe before retry; reconcile same task identities if post-commit file changed.','Blind repeating an edit is not the implemented safe recovery.'),
  T('plan draft','approve','first read reconciles; interactive confirmation eligible','plan draft awaiting confirmation','Prompt with 60-second bound.'),
  T('plan draft awaiting confirmation','approval confirmed','live lease; second read same hash','approved execute','Persist approved revision with execute mode before updating owned in-memory state.'),
  T('plan draft awaiting confirmation','cancel/timeout/stale/file drift','any guard fails','plan draft','Return refusal, preserve plan file and restrictions; re-read and ask again if needed.'),
  T('plan draft','cancel plan','current owner','cancelled execute','Persist execute/draft revision; preserve plan file.'),
  T('plan draft or approved execute','status/restore cannot validate file or owner','read failure, session mismatch, malformed state','ownership lost then unowned execute','Clear owned plan and fall back to execute mode.','This is a loss-of-restriction fallback, not proof that a plan was approved; preserve an explicit unavailable state in a future change.')
  ])

M('S04','Pi background job manager',
  'In-memory job map, FIFO reservations, four nonterminal capacity; bounded output tails; recent terminal retention; disposed flag.',
  'queued;active;completed;failed;cancelled;timed-out;disposed',
  [PI+'background-jobs.ts|background job manager and runtime|1-923'],[
  T('none','reserve job','not disposed; fewer than four nonterminal jobs','queued','Allocate ID and bounded output/metadata record; capacity counts queued jobs.'),
  T('queued','managed child readiness + handshake','current job and lease','active','Send launch input; close stdin; arm per-job timeout; append bounded output tail (65,536 bytes).'),
  T('queued or active','child closes zero','containment cleanup verified','completed','Freeze terminal record, finish waiter and release capacity; keep bounded recent results.'),
  T('queued or active','child error/nonzero','cleanup verified','failed','Store sanitized failure and bounded output; release capacity.'),
  T('queued or active','user cancels / timer fires','current nonterminal job','cancelled or timed-out','Terminate tree and verify cleanup before recording terminal state.'),
  T('terminal','duplicate settle/cancel','same terminal record','same terminal','Idempotent terminal result; do not relaunch or change completed result.'),
  T('terminal collection','retention exceeded','default 32, bounded configurable maximum 64','terminal collection pruned','Drop oldest retained terminal records; nonterminal jobs stay.'),
  T('manager','dispose','lifecycle ended','disposed','Clear manager state; reject new jobs.','Process ownership cleanup belongs to runtime, not deleting this map.')
  ])

M('S05','Pi managed background containment, audit and health',
  'Runtime healthy/disposed/stopping flags; pending spawn ownership set; cached settling promises; controller launch reservations and watcher/audit state.',
  'healthy;launch pending;running;settling;unhealthy;stopping;disposed',
  [PI+'background-jobs.ts|managed background runtime|1-923',PI+'native-background.ts|native controller|1-413'],[
  T('healthy','launch request','trusted lease and four-slot reservation available','launch pending','Reserve before awaiting spawn; record pending ownership; start managed process tree.'),
  T('launch pending','process admitted','readiness/handshake and lease valid','running','Mark job active; close stdin; install deadline and terminal observer.'),
  T('launch pending','audit launch fails','process may already exist','settling then unhealthy','Cancel child; latch controller unhealthy; suppress success.'),
  T('running or launch pending','finish/cancel/timeout/stop','job not already settling','settling','Cache one settling promise; terminate and verify tree; wait for in-flight spawn ownership before disposal.'),
  T('settling','verified containment','cleanup result clean','healthy or stopping','Publish terminal job state; audit terminal result; notify host; release slot.'),
  T('settling','cleanup cannot be verified','refused/failed cleanup','unhealthy','Latch unhealthy and retain unresolved/nonterminal evidence.','Cached settling promise prevents an independent cleanup retry; recovery is reload/new runtime, not another ordinary job action.'),
  T('terminal watcher','terminal audit fails','outcome exists but audit failed','unhealthy','Keep failure separate from process outcome; block further controller actions.'),
  T('healthy or unhealthy','stop lifecycle','invalidate lease first','stopping','Await pending admissions and settle all owned processes.','Dispose manager only after verified cleanup; unresolved containment is not silently cleared.'),
  T('stopping','all owned processes clean','no pending ownership','disposed','Release runtime/controller resources; next session builds a fresh controller.')
  ])

M('S06','Pi activity projection',
  'Active/recent maps keyed by kind and ID, timestamps, disposed flag; no durable authority.',
  'absent;active;recent completed;expired;disposed',
  [PI+'activity.ts|activity registry|1-254',PI+'sidebar-data.ts|activity projection|1-73'],[
  T('absent','start','not disposed','active','Insert activity; cap active projection at 16.'),
  T('active','complete','matching activity key','recent completed','Move to recent collection; cap at eight.'),
  T('recent completed','duplicate completion','same key','recent completed','Ignore duplicate completion.'),
  T('active or recent','snapshot/prune','active age >2h or recent age >5m','expired','Evict display entry; does not cancel a process or revoke authority.'),
  T('any','dispose','session lifecycle ends','disposed','Clear maps; suppress further display updates.')
  ])

M('S07','Pi subagent dispatch and aggregate outcome',
  'Catalog-derived roles; chain/parallel queue; per-child result; aggregate byte count; abort signal; activity records.',
  'unvalidated;queued;running;accepted;changes_requested;blocked;degraded;crashed;protocol-error;oversized;timed-out;cancelled;depth-exceeded',
  [PI+'dispatch.ts|dispatch single/chain/parallel|1-572',PI+'roles.ts|catalog role admission|1-69',PI+'contracts.ts|result contract|1-260'],[
  T('unvalidated','dispatch','live parent authorization; valid role/catalog; depth ≤4; ≤8 requests; ≤1 author','queued','Choose single/chain/parallel mode; prepare redacted request and activity.','Invalid mode/role/depth/shape returns explicit protocol or depth outcome before child launch.'),
  T('queued','scheduler admission','≤4 parallel child processes','running','Run isolated child under its role/tool contract and cancellation scope.'),
  T('running','valid final JSON','exact required shape and judgment','accepted / changes_requested / blocked','Preserve role judgment and structured output; best-effort audit.'),
  T('running','runtime failure','timeout/cancel/overflow/protocol/process failure','matching technical terminal','Sanitize output; retain distinct terminal type; verify cleanup in runner.'),
  T('chain child terminal','next child requested','previous judgment is accepted, changes_requested OR blocked','next queued','Pass redacted prior result into next role.','Technical terminal results stop the chain; a blocked review judgment alone does not stop it.'),
  T('parallel queue','abort','not yet started','cancelled','Do not spawn queued children; running children receive cancellation.'),
  T('children terminal','aggregate','combined payload ≤262,144 bytes','aggregate terminal','Priority order is cancelled > timed-out > depth-exceeded > oversized > protocol-error > crashed > degraded > blocked > changes_requested > accepted.'),
  T('any dispatch','finally','all started/queued activity items','display completed','Complete activity projection even for children that never ran.','Display completion is not evidence of execution or acceptance.')
  ])

M('S08','Pi private artifact approval process',
  'One-shot process flag; pending artifact/schema/hash/revision plus generation UUID; trusted TUI lease; consumed state.',
  'inert process;pending prompt;phrase matched;consuming;consumed;cancelled;stale;refused;outcome unknown',
  [PI+'approval-entry.ts|private entry|1-65',PI+'approval-dialog.ts|approval dialog and consume|1-103'],[
  T('inert process','private entry starts','strict inert launch flags, tools=[], no extra extensions/skills/prompts/themes/context/session; runtime exactly 1.0.2','pending prompt','Load one private approval request; ordinary prompt/LLM flow is unavailable.','Ordinary installed Pi flows are refused; supported host compatibility elsewhere is 1.1.0, so this entry is not a supported ordinary authority adapter.'),
  T('pending prompt','show prompt','trusted TUI; current session UUID/lease; exact pending artifact identity','pending prompt','Allow bounded human input for five minutes; show exact armed phrase.'),
  T('pending prompt','cancel/timeout/unmatched phrase','phrase differs or lease stale','cancelled or stale','Do not consume authorization; return explicit refusal.'),
  T('pending prompt','exact phrase','current pending hash/revision/generation','phrase matched then consuming','Consume pending approval once through bridge, bound to generation UUID.'),
  T('consuming','confirmed consume response','same current lease','consumed','Return proof of the one consumed approval; shutdown one-shot process.'),
  T('consuming','response lost or lease stale after consume','effect may already be committed','outcome unknown','Do not infer that approval failed; re-observe durable authorization before any retry.'),
  T('any terminal','finally','one-shot lifecycle','shut down','Always terminate private entry, without ordinary agent continuation.')
  ])

M('S09','Pi child RPC admission and runner protocol',
  'Runner phase; nonce/challenge; runtime identity and manifest digest; broker authorization; task submission/agent markers; bounded stream buffers; timer/abort; managed process handle.',
  'preflight;environment prepared;spawn admission;attestation pending;handshake confirmed;task submitted;agent running;result captured;settled;completed;degraded',
  [PI+'runner.ts|run isolated child|1-1030',PI+'child-extension.ts|bootstrap and protocol hooks|1-223',PI+'attestation.ts|attestation format|1-31'],[
  T('preflight','run request','active trusted Node/Pi identity; catalog charter/tools; canonical cwd; depth/size valid','environment prepared','Mint nonce/challenge; bind broker; create private child home/session files; authorize exact selected provider.','Any preflight mismatch refuses before prompt/task execution.'),
  T('environment prepared','managed spawn','inert RPC offline argv with --no-approve and exact extension','spawn admission','Start child behind managed tree admission; await readiness before sending authorization material.'),
  T('spawn admission','child bootstrap','child capability not consumed','attestation pending','Consume bootstrap capability once; load built-in tool contracts; send digest-bound attestation and UI prompt.'),
  T('attestation pending','parent validates then confirms','nonce/challenge/digest/identity exact','handshake confirmed','Parent sends confirmation; child acknowledges one handshake.','Wrong ordering/replay/mismatch becomes fixed degraded protocol error; consumed capability is not retried.'),
  T('handshake confirmed','task prompt and acknowledgment','current lease and not aborted','task submitted','Send authorized task once, then await agent_start.'),
  T('task submitted','agent_start','expected sequence','agent running','Collect authorized stream/tool events within limits.'),
  T('agent running','agent_end','willRetry=false; exact assistant stop/model/provider; nonempty valid non-sensitive output','result captured','Capture candidate final text.','Early stop, retry marker, unexpected provider or sensitive output does not count as completion.'),
  T('result captured','settled event','aborted=false and sequence exact','settled','Close stdin and await child close.'),
  T('settled','close code 0 + verified tree cleanup','all protocol edges seen','completed','Return bounded final result.'),
  T('any nonterminal','abort/deadline/line or stream overflow/protocol error/process error','any terminal fault','degraded or typed failure','Terminate and verify process tree; return fixed sanitized diagnosis.','Limits: line 65,536; stdout 1 MiB; stderr 16 KiB; result 65,536. Parent lease drift never returns successful stale result.'),
  T('child ready','write/edit/bash invocation','default execute policy, RPC UI, no delegated confirmation/audit','blocked','Final tool guard refuses mutator because confirmation UI is unavailable.','Read tool works. Author tool catalog therefore overstates usable mutation capability; preserve guard and add explicit scoped delegation if authoring is intended.')
  ])

M('S10','Pi child environment and credential lifetime',
  'Private root directory; retained credential-file handle; selected provider model configuration; parent-only broker credential; cleanup attempt counter.',
  'unprepared;private root created;validated;child-ready;cleanup pending;cleaned;cleanup failed',
  [PI+'child-env.ts|prepare child environment and cleanup|1-908'],[
  T('unprepared','prepare','canonical validated roots','private root created','mkdtemp; construct allowlisted baseline environment and isolated home/agent/session locations.'),
  T('private root created','operator/provider config read','bounded valid shapes; supported provider','validated','Resolve only selected provider; parent retains actual upstream endpoint/key/headers; child receives loopback URL and opaque capability token.'),
  T('private root created','unsupported provider or malformed models/config','AWS/Vertex/Copilot/Codex/OAuth or invalid shape','refused','No provider passthrough; do not expose parent credentials.','Environment construction before the cleanup try can leave an empty root on early failure; later admission failure suppresses cleanup errors.'),
  T('validated','write isolated models','exclusive new credential-bearing file','child-ready','Write minimal model config with retained file handle; no broad inherited home/session context.'),
  T('child-ready or partial prepare','cleanup','child scope finished','cleanup pending','Truncate retained handle, remove named file, then recursive root cleanup with up to five bounded retries.'),
  T('cleanup pending','all sensitive remnants removed','verified filesystem operations','cleaned','Close retained ownership and release root.'),
  T('cleanup pending','retries exhausted','filesystem refuses cleanup','cleanup failed','Throw explicit cleanup error.','Do not report successful sanitization merely because the child exited; retain path diagnosis without credentials.')
  ])

M('S11','Pi inference broker authorization and stream forwarding',
  'Loopback HTTP server; random token+nonce; unset or authorized upstream; revoked/closed state; active sockets; cached close promise.',
  'listening unarmed;authorized;forwarding;revoked;closing;closed',
  [PI+'inference-broker.ts|broker lifecycle|1-510'],[
  T('none','create broker','loopback only, ephemeral port','listening unarmed','Bind port zero; mint token/nonce; reject inference until upstream authorized.'),
  T('listening unarmed','request','upstream unset','same','Return 503; no upstream request.'),
  T('listening unarmed','authorize','exact selected provider/route and parent-owned credential','authorized','Install narrowly scoped upstream configuration; child never receives actual key.'),
  T('authorized','child request','exact capability token/nonce, route/method/body/header constraints','forwarding','Proxy to allowed upstream and scan output with 4,096-byte overlap for forbidden sensitive material.','Bad request fails before forwarding; upstream failure sanitized.'),
  T('forwarding','sensitive or invalid response','scanner or header guard fails','authorized or request failed','Return 502 if headers not sent; otherwise destroy partial response stream.','Partial stream delivery is possible before late detection; no success classification follows.'),
  T('authorized or forwarding','revoke','lifecycle invalidated','revoked','Block future requests; existing socket handling is separate.'),
  T('any open','close','cleanup requested','closing then closed','Revoke, destroy active sockets and close server; share cached close promise.','Repeated close is idempotent; no reauthorization after close.')
  ])

M('S12','Pi runtime identity and import admission',
  'Canonical active CLI/Node/package/export metadata; WeakSet of issued identities; cached lazy metrics promise.',
  'unresolved;validated identity;import pending;admitted;refused',
  [PI+'runtime-resolver.ts|resolve/revalidate active runtime|1-208',PI+'compatibility.ts|supported runtime|1-43',PI+'extension.ts|load metrics library|1-1130'],[
  T('unresolved','resolve active runtime','canonical active CLI; supported package/version/exports and Node executable','validated identity','Issue opaque identity object; no arbitrary PATH runtime substitution.'),
  T('validated identity','import Pi API/metrics','identity issued by resolver and pre-import revalidation passes','import pending','Import exact resolved module; concurrent metrics callers share one pending promise.'),
  T('import pending','module loaded','post-import identity revalidation and required exports/VERSION pass','admitted','Return trusted exports bound to current runtime.'),
  T('any admission','path/version/export/identity drift','guard fails','refused','Fixed diagnosis; no alternative runtime fallback.','Lazy metrics failure clears pending cache so a subsequent request may retry, but identity guards remain.'),
  T('admitted','later use','identity revalidated at authority boundary','admitted or refused','Recheck actual executable/package identity; cached JavaScript object alone is insufficient authority.')
  ])

M('S13','Pi managed process trees and platform admission',
  'Managed process phase, PID/group/job identity, readiness promise, cached terminate promise; Windows supervisor admission transcript.',
  'spawning;admitting;ready;terminating;clean;refused;cleanup failed',
  [PI+'process-tree.ts|managed process tree|1-1005',PI+'windows-supervisor.ts|supervised launch and parent leash|1-242'],[
  T('spawning','POSIX child spawn','detached process with valid group identity','ready','Own process group before handing execution authority to caller.'),
  T('spawning','Windows inert supervisor starts','bounded environment/launch material','admitting','Wait STARTING→COMPILED→PID_ACCEPTED→ATTACHED; idle bound 15s and absolute bound 30s; transcript ≤64 records.','No target launch before JobObject attachment.'),
  T('admitting','launch payload then exact START','fd4 ≤3 MiB; fd5 exact START ≤16 bytes; env ≤256 entries/262,144 bytes','ready','Supervisor launches child and emits STARTED/WATCHING; parent leash remains active.'),
  T('admitting','bad order/timeout/parent death','any failed admission guard','refused','Fail closed before target authority; cleanup supervisor and job.'),
  T('ready','terminate','first termination request','terminating','Cache one termination promise. POSIX SIGTERM then 500ms grace, SIGKILL and 2s verification; Windows taskkill/root plus JobObject close and root/supervisor verification.'),
  T('terminating','absence verified','owned group/job no longer live','clean','Resolve cleanup success; later terminate calls reuse result.'),
  T('terminating','unverifiable ownership/liveness','checks fail or process remains','cleanup failed','Return refused/failed result; caller must not call this clean.','Cached termination result offers no new cleanup attempt by itself.'),
  T('Windows ready','parent leash closes','parent vanished','terminating then refused','Supervisor fails closed (70) and job cleanup removes child tree.'),
  T('Windows ready','child exits','normal managed child','terminal','Drain read/write streams for bounded 500ms each; preserve exit code, use 71 for missing code; refusal flush bounded 500ms before 70.')
  ])

M('S14','Pi Python bridge process request lifecycle',
  'Cached validated bridge paths; one request process; first failure reason latch; stdout/stderr bounds; timeout/abort handlers; close/backstop.',
  'unavailable;ready;request running;failure latched;closed;backstop resolved',
  [PI+'bridge.ts|BridgeClient and bounded process collection|1-940'],[
  T('construct','validate paths','canonical project/home/package; home outside project; trusted Python/Git','ready or unavailable','Resolve bridge executable/package once.','Constructor validation failure is cached; call does not auto-resolve a new installation.'),
  T('ready','call','request ≤262,144 bytes; not pre-aborted','request running','Spawn trusted Python in package cwd with minimal environment; write one JSON request.'),
  T('ready','call pre-aborted','signal already aborted','ready','Return cancellation failure without spawn.'),
  T('request running','timeout/abort/output overflow','10s deadline; each bounded stream','failure latched','Preserve first reason; kill tree via POSIX SIGKILL or Windows taskkill; start 2s backstop.','Bridge kill result does not carry the stronger verified-containment state used by managed child runner.'),
  T('request running','process close','zero exit and valid JSON/envelope','closed','Return bridge result; caller decides hard block versus degradation.'),
  T('request running','nonzero/error/malformed envelope','any failure','closed','Return bounded sanitized failure; mutation gate refuses; lifecycle/read refresh may warn/degrade.'),
  T('failure latched','close OR 2s backstop','whichever observed first','closed or backstop resolved','Return original failure even if process never emitted close.','A resolved bridge promise is not evidence that all descendants are gone.')
  ])

M('S15','Pi usage extraction cursor and delivery acknowledgment',
  'Cursor initially -1, session identity, entry positions, range count and accepted-through acknowledgment; current read snapshot.',
  'unscanned;range collected;delivery pending;acknowledged;retry pending;more pending',
  [PI+'bridge.ts|usage extraction and cursor advancement|1-940'],[
  T('unscanned or acknowledged','refresh usage','same session identity before/after reading entries','range collected','Scan at most 256 entries per range; extract only valid assistant usage facts with raw positions.'),
  T('range collected','submit bridge usage','bounded valid facts/range','delivery pending','Send session identity and exact scan range; do not advance local cursor yet.'),
  T('delivery pending','acknowledgment','acceptedThrough==scanEnd and high-water within observed entry bounds','acknowledged','Advance cursor to acknowledged raw position; preserve exact duplicate-resistant range identity.'),
  T('delivery pending','bridge failure or invalid acknowledgment','ack does not prove range acceptance','retry pending','Keep last acknowledged cursor; next refresh resends exact range.','Do not drop facts by treating attempted delivery as accepted.'),
  T('range loop','maximum ranges reached','entries remain','more pending','Return morePending=true; continue in later refresh without skipping.'),
  T('scan','session changed or no entries','identity mismatch or empty session','unscanned or unchanged','Suppress mixed-session snapshot; no empty success snapshot is invented.')
  ])

M('S16','Pi local audit append durability and approval dependency',
  'Pinned canonical directory; opened file inode/link identity; bounded row; create/open mode; pre/post-write observations.',
  'unopened;opened;appending;durable;unverified append;refused',
  [PI+'audit-sink.ts|append audit row|1-187'],[
  T('unopened','append row','redacted one-line row ≤2,048 bytes; canonical trusted directory','opened','Open existing regular single-link target or exclusive-create new target.'),
  T('unopened','create races existing file','EEXIST on create','opened or refused','Retry once through existing-file validation.'),
  T('opened','append','same inode/path/link identity before write','appending','Append bytes, fsync, verify size and file/path identity after write.'),
  T('appending','post-write checks pass','expected append size/identity','durable','Return true to caller.'),
  T('appending','fsync/post-write check fails','bytes may already exist','unverified append','Return false.','False is not proof that no row was written. Approved permission audit false blocks tool mutation; less critical audit callers are best effort.'),
  T('unopened or opened','unsafe path/file/row','guard fails','refused','Return false without claiming audit persistence; do not follow linked targets.')
  ])

M('S17','Pi compaction proposal and host confirmation',
  'Trusted lifecycle lease; context fingerprint; prior compaction fingerprint; bounded semantic descriptors; proposed summary; recent confirmation audit IDs.',
  'unexamined;eligible prefix;no-op;child summarizing;proposal ready;host confirmed;stale/refused',
  [PI+'compaction.ts|compaction planning and event handlers|1-533'],[
  T('unexamined','compaction request','trusted lease; bounded ≤100,000 context descriptors; semantic IDs unique','eligible prefix','Plan prefix pruning while keeping final ten messages and protected tail; bound compacted prefix to 8,192 descriptors.'),
  T('eligible prefix','plan validates','zero removable prefix/already compacted/same prior fingerprint','no-op','Return no change; no child launch.'),
  T('eligible prefix','plan validates actionable','protected tail/actions/metrics/fingerprint consistent','child summarizing','Serialize redacted prefix ≤48KiB, previous summary ≤8KiB and custom instructions ≤4KiB; run isolated child with no tools or skills.'),
  T('child summarizing','valid bounded summary','≤16KiB; same lease/fingerprint','proposal ready','Return compaction proposal; the host, not this helper, mutates conversation context.'),
  T('child summarizing','abort/stale/error/invalid summary','any fault','stale/refused','Throw or suppress proposal; no partial context mutation.'),
  T('proposal ready','host confirms compaction event','matching event identity','host confirmed','Best-effort audit; retain 16 recent confirmation identities to deduplicate.'),
  T('host confirmed','duplicate host event','already recorded identity','host confirmed','Do not duplicate confirmation audit.')
  ])

M('S18','Pi footer installation and serialized refresh',
  'Footer lifecycle generation, active instance/native footer ownership; queued refresh promise; usage/governance/git snapshots and cursor.',
  'native;install pending;installed;refreshing;degraded/native fallback;disposed',
  [PI+'footer.ts|footer integration|1-489',PI+'footer-state.ts|footer projection|1-230',PI+'git-facts.ts|bounded Git observations|1-150',PI+'status.ts|status projection|1-274'],[
  T('any','start session','interactive hasUI and mode absent/TUI','install pending','Dispose prior generation; await metrics library; retain native footer until safe installation.'),
  T('install pending','metrics ready','generation still current','installed','Install owned footer; guard against stale async completion.'),
  T('install pending','metrics unavailable/noninteractive/stale','cannot safely install','degraded/native fallback','Keep native footer and bounded notice; stale completion does nothing.'),
  T('installed','refresh','current lease/generation','refreshing','Serialize refreshes; softly prepare bridge; independently await usage/governance/Git using allSettled.'),
  T('refreshing','partial data success','same current lifecycle','installed','Use fulfilled usage cursor; keep prior governance if a trusted refresh fails; clear governance if inactive/untrusted; unavailable Git remains unknown.'),
  T('refreshing','stale completion','generation changed','disposed or newer installed','Ignore result rather than overwrite new session.'),
  T('any footer','dispose','owned instance','disposed then native','Advance generation; release subscription and restore native footer only if owned.')
  ])

M('S19','Pi sidebar manager and compositor ownership',
  'Registered/installed/autoinstall flags, width choice, compositor private columns/doRender hooks, raw terminal width, painter error count; manager lacks async generation token.',
  'unregistered;registered;install pending;installed;too narrow/off;disposed;resurrected after disposal',
  [PI+'sidebar-manager.ts|register, autoInstall, dispose|1-212',PI+'sidebar-compositor.ts|private hook compositor|1-323',PI+'sidebar.ts|sidebar rendering|1-314'],[
  T('unregistered','register','trusted TUI','registered','Register sidebar command once; preserve user width choice between 24 and 60 columns in memory.'),
  T('registered','autoInstall','footer TUI available; raw width ≥120; first automatic decision','install pending','Await metrics and install compositor if terminal capability probe passes.'),
  T('registered','autoInstall narrow','raw width <120','too narrow/off','Record automatic decision; user may later toggle explicitly.'),
  T('registered or off','user on/toggle','trusted TUI and enough raw width for sidebar +60','install pending then installed','Patch configurable columns getter/doRender; reserve sidebar width; paint alongside main UI.'),
  T('installed','resize/width choice','live compositor','installed or disposed','Update derived width; bounded painting; unsupported metrics or repeated invalid paint (three) dispose; exception disposes and warns once.'),
  T('installed','off/dispose','owned patches','disposed','Restore only hooks still owned by compositor; preserve third-party replacement hooks.'),
  T('install pending','dispose before metrics resolves','manager resets flags but does not invalidate pending await','disposed','Current compositor disposed, but pending install remains alive.'),
  T('disposed with pending install','metrics promise resolves','missing lifecycle generation check','resurrected after disposal','Install fresh compositor, patch terminal columns/doRender, mark installed=true after disposal.','Confirmed isolated probe: 140 columns→99 after dispose; final second dispose restores 140. Mirror footer generation guard to prevent this.')
  ])

M('S20','Pi command ownership, notices and diagnostics',
  'Canonical catalog ownership snapshot; command registered/degraded state; bounded notice IDs; doctor health aggregation.',
  'unregistered;owned;degraded;invocation loading;prompt queued;diagnosed',
  [PI+'command-ownership.ts|ownership inspection|1-201',PI+'commands.ts|command adapters|1-129',PI+'notices.ts|deduplicated notices|1-81',PI+'doctor.ts|doctor facts and outcome|1-502'],[
  T('unregistered','register command','catalog/skill/extension canonical ownership exact','owned','Register only eligible surfaced commands; preserve native replacements.'),
  T('owned','invoke','live lease and current command ownership at entry','invocation loading','Read bounded UTF-8 skill, strip frontmatter, reject unsafe closing skill tag; doctor can generate dedicated content.'),
  T('invocation loading','read succeeds','valid body','prompt queued','sendUserMessage as follow-up; this queues workflow text rather than executing its claimed lifecycle.','No post-await lease recheck at this adapter boundary; source ownership was checked before await.'),
  T('invocation loading','read/ownership failure','guard fails','degraded','Report actionable command failure and retain degraded flag; no workflow prompt success.'),
  T('any notice set','append notice','normalized rule/body ID not already present','same + notice','Deduplicate owned notice identity; bounded 16KiB projection.'),
  T('any','doctor','read-only observations and H03 dry-run probe','diagnosed','Aggregate unhealthy > degraded > healthy; active dispatch is always degraded while running.','Doctor reports observed capability; it does not grant tool authority or repair state.')
  ])

M('S21','Pi source-checkout farm adapter',
  'Authorized lease; source checkout freshness check; managed farm subprocess; bounded output; cancellation/cleanup status.',
  'preflight;running;completed;failed;cancelled;cleanup unknown',
  [PI+'farm.ts|farm dispatch adapter|1-278'],[
  T('preflight','farm invocation','current authority; canonical plan inside repo; adjacent Claude farm.js present and no more than 1s stale','running','Resolve exact Node; filtered environment; recheck lease after async runtime resolution; spawn managed farm subprocess.','Installed isolated Pi package without adjacent Claude source bundle is unsupported; no implicit inline promotion.'),
  T('running','normal close','bounded output ≤65KiB; verified cleanup','completed or failed','Return original farm exit/result plus sanitized bounded output.'),
  T('running','abort/deadline/overflow','terminal event','cancelled or failed','Terminate managed tree and verify cleanup.'),
  T('settling','cleanup unverified','process containment unknown','cleanup unknown or cancelled','Return failure details; cancellation result priority can mask cleanup-specific headline.','Preserve cancellation and containment as separate result fields in future contracts.')
  ])

FARM='plugins/ca/tools/'
M('S22','Farm typed artifact admission and pinned engine execution',
  'Plan origin, sibling HTML/binding directories, authoring/projection digests; pinned release manifest/binary handle; verification phase.',
  'legacy admitted;typed unverified;installed payload checked;engine pinned;authoring verified;dispatch sealed;refused',
  [FARM+'farm.ts|installedArtifactBinary, verifyArtifactPlan and pinned invocation|195-650'],[
  T('input plan','classify artifact origin','no sibling HTML or artifact binding evidence','legacy admitted','Retain legacy JSON plan behavior without requiring typed artifact engine.'),
  T('input plan','classify artifact origin','HTML-backed or bound projection','typed unverified','Require native verification before canary, worktrees, worker requests or dispatch effects.'),
  T('typed unverified','load installed engine','real bounded installation and exact release manifest shape/protocol/schema; native_tested platform; hash/magic match','installed payload checked','Read manifest and binary from plugin helpers/artifacts only; no PATH/download/build fallback.','Current farm requires exact five-key manifest; qualified package adds context_qualification and is rejected before execution.'),
  T('installed payload checked','pin executable','matching canonical file/bytes','engine pinned','Linux executes pinned fd; macOS uses private verified bytes; Windows read-sharing pin guard holds handle and READY handshake.'),
  T('engine pinned','canary verification','authoring binding exact','authoring verified','Ask engine to verify authoring identity before economic model probes.'),
  T('engine pinned','ordinary dispatch verification','enriched projection digest and provider seal exact','dispatch sealed','Verify exact dispatch payload and bound provider; only then allow work scheduling.'),
  T('any typed admission','shape/hash/path/protocol/binding/pin error','guard fails','refused','Stop before farm side effects; close pin handles/private files.','Do not reinterpret typed evidence as legacy JSON on failure.')
  ])

M('S23','Farm run scheduler, dependency state and circuit breaker',
  'Task plan DAG; pending/running/settled maps; file-scope reservations; shared worker limiter; run directory and JSONL/latest/report files; breaker and abort flags.',
  'validating;initializing;pending;running;green;escalated;blocked;aborted;reporting;complete;receipt failed',
  [FARM+'farm.ts|main/run scheduler and report finalization|3000-3697'],[
  T('validating','start farm','closed plan schema; unique IDs; valid dependency DAG; selected provider URL/config','initializing','Resolve config precedence env > plan > defaults; validate HTTPS/no embedded credentials; mint or accept FARM_RUN_ID.'),
  T('initializing','create run workspace','paths contained and directories usable','pending','mkdir run directory recursively; truncate stream file; force integration branch to configured base; create run-scoped integration worktree.','Explicit reused run ID is not exclusive and can overwrite prior evidence; fresh invocation is not resume.'),
  T('pending','schedule task','all dependencies green; no reserved lexical file-scope conflicts; concurrency capacity','running','Reserve task scope before launch; start task pipeline, sharing worker limiter with best-of-N samples.'),
  T('pending','dependency escalated/blocked','dependency cannot become green','blocked','Record non-executed task result; never claim worker execution.'),
  T('running','task settles','Result.status green or escalate','matching terminal','Record result, append JSONL, best-effort latest summary, release reservations; permit newly unblocked tasks.'),
  T('running scheduler','breaker threshold','settled tasks ≥ configured minimum (default 3), escalation fraction > configured rate (default 0.5)','draining with aborted=true','Stop new admission; let existing tasks settle without cancelling them; mark remaining tasks blocked/not scheduled.'),
  T('any scheduling','external OS termination','no cooperative farm CLI signal handler','process terminated / durable outcome uncertain','OS interruption may stop process before finally/receipt completes.','report.aborted is only set by circuit breaker; do not infer a durable abort receipt from process death.'),
  T('all admitted tasks settled','finalization','including exceptions','reporting','Verify integration-worktree cleanup; write durable run report then Markdown; latest convenience copies are best effort.'),
  T('reporting','tier-one receipts succeed','all tasks green and cleanup verified','complete exit 0','Return all-green success.'),
  T('reporting','tier-one receipts succeed','escalation/block/abort or cleanup degradation','complete exit 2','Preserve partial successes with actionable failure outcome.'),
  T('reporting','tier-one receipt write fails','task/integration effects may already be committed','receipt failed exit 3','Return unverified publication outcome; original branches/commits still exist.','Re-dispatch can force-reset integration and replace task branches; recover receipt from actual refs/run evidence first.'),
  T('run body','unexpected exception','outside handled per-task failure','failure exit 1','Finally attempts cleanup/report.','Outer error may dominate report failure; preserve independent workload, cleanup and receipt axes.')
  ])

M('S24','Farm per-task author/gate/retry lifecycle',
  'Deterministic task worktree and branch; attempt index/retry budget; setup fingerprint; initial read-only test hashes; drift count; captured worker/gate failure.',
  'preparing;setup;authoring;materializing;checking;retry pending;ready to commit;escalated;aborted',
  [FARM+'farm.ts|prepareWorktree, runTask, checkDrift, runGate|650-3050',FARM+'worktree-fs.ts|safe materialization|1-194'],[
  T('preparing','task start','canonical worktree path inside approved root','setup','Under worktree lock remove prior task worktree, delete task branch, add new branch/worktree at base.','This destructively replaces same task ID resources; failed remove/delete may be ignored until add fails.'),
  T('setup','run setup','first attempt or setup fingerprint changed or setupEachAttempt','authoring','Run configured setup; fingerprint commands and declared setup inputs; ignored dependencies can survive resets.'),
  T('setup','setup command fails','any setup failure','escalated','Stop task immediately; leave inspection worktree.','No author quality retry is used to repair a setup failure.'),
  T('authoring','worker returns valid files','current request successful','materializing','Write only admitted file paths using symlink-resistant writer; capture patch/output/evidence.'),
  T('materializing','files written','read-only tests unchanged and post-write sweep safe','checking','Check actual worktree drift, gates, anti-gaming heuristic and optional mutation evidence.'),
  T('materializing or checking','unsafe file/test mutation','path escape, link race, protected initial test changed','escalated','Fatal refusal; do not retry a potentially unsafe materialization.'),
  T('checking','drift outside scope','first occurrence and retry budget remains','retry pending','Explain actual drift; reset task worktree to current base and retry worker.'),
  T('checking','drift repeats or no budget','second drift or exhausted budget','escalated','Retain worktree/evidence for inspection.'),
  T('checking','Git drift commands fail','diff/ls-files nonzero','checking with empty drift result','Current checkDrift collapses read failures to empty lists.','Unknown worktree observation can be treated as clean; preserve an explicit read failure instead.'),
  T('authoring or checking','retryable worker/gate/quality failure','budget remains and no fatal containment flag','retry pending','Reset hard/clean as configured; preserve setup cache policy; feed bounded failure into new attempt.'),
  T('authoring','nonretryable HTTP cooldown','transport retryable=false','escalated','Do not spend author attempts immediately against a long rate-limit window.'),
  T('checking','gate subprocess cleanup failed','runGate sees nonzero exit only','retry pending or escalated','runGate currently drops cleanupFailed into ordinary gate failure.','Unlike mutation handling, outer author retry can proceed without verified gate containment.'),
  T('checking','all checks pass','no fatal mutation/heuristic issue','ready to commit','Continue to commit/integration lifecycle.'),
  T('any nonterminal','attempts exhausted','retry budget exhausted','escalated','Stop retrying; keep task worktree for diagnosis unless explicit successful cleanup path applies.')
  ])

M('S25','Farm best-of-N sample selection and cleanup',
  'Frozen task branch base; per-sample isolated worktrees/branches; shared worker limiter; ordered candidate results; winner materialization; cleanup diagnostics.',
  'sampling;candidate checked;selecting;winner materialized;no winner;cleanup pending;cleanup degraded',
  [FARM+'farm.ts|best-of-N sampling and selection|2000-3050'],[
  T('sampling','launch samples','same frozen base; separate sample worktrees; shared worker capacity','candidate checked','Each sample runs setup→worker→safe materialization→protected-test/drift/gate checks independently.'),
  T('sampling','all samples settle','all launched samples awaited','selecting','Order green candidates by sample index, not fastest arrival; retain best failure and deferred transport signal.'),
  T('selecting','eligible candidate','sample green','winner materialized','Reset task worktree, copy candidate patch and run full task checks again; try later candidate if a nonfatal materialization/check fails.'),
  T('selecting','fatal candidate failure','unsafe write/test/containment issue','no winner','Do not continue alternatives across a fatal safety failure.'),
  T('selecting','first rechecked candidate passes','full task pipeline green','winner selected','Use that candidate; do not run additional author samples.'),
  T('selecting','no passing candidate','all checked or deferred without winner','no winner','Feed best bounded failure into outer retry; deferred cooldown only stops when no winner exists.'),
  T('any sample outcome','finally','every sample resource','cleanup pending','Verify removal of every sample worktree and branch, even losing/cancelled samples.'),
  T('cleanup pending','remaining resource exists','cleanup retries exhausted','cleanup degraded','Attach leak diagnostics.','A task can remain green while run exits 2 for cleanup degradation; preserve both dimensions.')
  ])

M('S26','Farm commit, merge and moving-base retry',
  'Task branch HEAD, integration branch/worktree, commit identity, merge lock, retry budget, refreshed read-only baseline.',
  'ready;staging;committed;merging;integrated;rollback checking;rebasing retry;fatal;cleanup',
  [FARM+'farm.ts|commit and integrate task|1800-3050'],[
  T('ready','stage task paths','validated explicit paths','staging','git add explicit paths, with up to three idempotent retries.'),
  T('staging','commit','staged intended changes','committed','Run commit once; retain branch HEAD.','Commit failure is not blindly repeated because commit may have succeeded despite lost observation.'),
  T('committed','integration lock acquired','single merge owner','merging','Merge task branch --no-ff into integration worktree.'),
  T('merging','merge exits zero','merge command success','integrated','Accept integration; no fresh integration gate is run in this success branch.','Per-task green is not evidence of a newly tested combined integration tree.'),
  T('merging','merge fails','conflict or Git failure','rollback checking','Abort merge and verify integration worktree clean before releasing/continuing.'),
  T('rollback checking','clean state cannot be verified','abort/readback failure','fatal','Stop task; do not reset/retry over unknown integration state.'),
  T('rollback checking','clean rollback and retry budget','integration HEAD can be pinned','rebasing retry','Capture prior attempt, reset task hard to current integration HEAD, clean untracked files, read back base and refresh protected-test hashes.'),
  T('rebasing retry','new base observed','same intended task identity','authoring','Run full author/check pipeline again on moved integration base.'),
  T('integrated','task cleanup','worktree removal verified','green','Remove worktree but keep task branch/commit; record green only after cleanup result handled.','Cleanup failure is explicit and can degrade the run even when commit/merge succeeded.')
  ])

M('S27','Farm HTTP worker transport and retry budget',
  'Attempt count (maximum three), request/body deadline, first failure class, Retry-After delay, response validation and sanitized usage.',
  'requesting;headers received;body reading;backoff;completed;retryable failure;deferred nonretryable',
  [FARM+'farm.ts|worker request/retry transport|900-1800'],[
  T('requesting','HTTP request','provider config valid; abort not set','headers received','Use bounded 120-second deadline covering request and response body.'),
  T('requesting','pre-header network failure','attempts remain','backoff','Retry internally with bounded exponential backoff (default ceiling 16s).'),
  T('headers received','429 or 5xx','attempts remain and cooldown fits local deadline','backoff','Parse Retry-After seconds or HTTP date; wait bounded delay; retry same worker request.'),
  T('headers received','429 cooldown too long / final 429','cannot honor locally','deferred nonretryable','Return retryable=false and cooldown guidance; outer author retry must not immediately resubmit.'),
  T('headers received','other non-2xx','not internally retryable','retryable failure','Return structured sanitized failure; outer author quality retry may still apply.'),
  T('headers received','2xx','response admitted','body reading','Read bounded body under same request deadline; validate model output schema/files.'),
  T('body reading','body failure / malformed response','cannot obtain valid result','retryable failure','No internal body replay; outer task may retry if budget remains.'),
  T('body reading','valid response','required output fields valid','completed','Return files/judgment/valid reported usage; redact credentials and unsafe raw error content.'),
  T('any request phase','finally/abort/deadline','terminal','terminal','Abort active request/stream so a timer or detached response does not continue work.')
  ])

M('S28','Farm anti-gaming and mutation evidence',
  'Eligibility/disabled flags; lexical overlap heuristic; mutation budget; backup file bytes; trial counts, upper bound and containment failure.',
  'not applicable;heuristic inspected;hook running;mutating;testing;restoring;verified evidence;unverified evidence;fatal',
  [FARM+'mutation.ts|mutation sweep and optional hook|1-529',FARM+'farm.ts|quality evidence integration|900-3050'],[
  T('task checked','mutation eligibility','disabled or no eligible source','not applicable','Return no mutation score; no test claim.'),
  T('task checked','lexical shared literal heuristic','tiny output/shared literal pattern ≤5','heuristic inspected','Flag high risk or warning according to heuristic.','This pattern is a suspicion signal, not proof of author intent or gaming.'),
  T('eligible','configured mutation hook','command present','hook running','Run bounded by gate timeout; accept score only with zero exit, no timeout and verified cleanup.'),
  T('hook running','valid adverse score','score ≤0.1 and at least five mutations','verified adverse evidence','Attach high-risk signal for outer task quality decision.'),
  T('hook running','malformed/error/timeout','no trustworthy score','unverified evidence','Warning rather than fabricate a positive score; preserve already-proven adverse evidence.'),
  T('hook running','cleanupFailed','containment unverified','fatal','Escalate without author retry.'),
  T('eligible','built-in sweep','≤15 sampled mutants within 30s budget','mutating','Backup original bytes; apply one mutation at a time.'),
  T('mutating','run first gate','remaining time available','testing then restoring','Test one mutant under remaining bounded budget, then restore original before next.'),
  T('testing','timeout/unclassified nonzero','not a classified mutation kill','unverified evidence','Exclude timed-out/unclassified trial from verified score; report upper bound when adverse earlier results already constrain it.'),
  T('testing','all trials survived','at least three valid trials','verified adverse evidence','Return score zero; fewer valid trials returns no score.'),
  T('any sweep','finally','backups exist','restoring','Restore every original file even on abort/failure.'),
  T('restoring','unsafe path or failed restoration','cannot prove original bytes restored','fatal','Stop task with explicit unsafe/fatal result; no clean score or blind retry.')
  ])

M('S29','Farm subprocess timeout and containment result',
  'Child PID/process group; timeout; stdout/stderr accumulation; kill/verification result; exit code and cleanupFailed.',
  'running;timed out;terminating;closed clean;closed cleanup unknown',
  [FARM+'exec.ts|run and treeKill|1-355'],[
  T('none','run command','spawn succeeds','running','Detached POSIX group; capture stdout/stderr. Git defaults to no timeout; setup/gates default 300s.'),
  T('running','ordinary close','no timeout','closed clean or ordinary failure','Return actual exit code and accumulated output.','Output strings are accumulated without a fixed cap in this helper.'),
  T('running','timeout','configured deadline elapsed','terminating','Kill tree and verify containment rather than return at timer edge.'),
  T('terminating','tree absence verified','cleanup result clean','closed clean with timeout','Return 124/timedOut=true/cleanupFailed=false.'),
  T('terminating','cleanup cannot be verified','process/group may remain','closed cleanup unknown','Return 125/timedOut=true/cleanupFailed=true.','Callers must carry cleanupFailed independently; runGate currently drops it.'),
  T('Windows termination','taskkill/fallback','platform-specific verification','clean or unknown','Attempt tree kill; fallback/root checks do not independently prove every descendant vanished.','Do not equate root-process death with descendant containment where proof is missing.')
  ])

M('S30','Farm worktree and branch cleanup',
  'Requested resource identity; worktree registry observation; filesystem observation; branch ref observation; up to three attempts.',
  'cleanup requested;removing;observing;clean;retry;degraded',
  [FARM+'farm.ts|verified worktree/branch cleanup helpers|1700-2050'],[
  T('cleanup requested','remove worktree','worktree lock acquired','removing','git worktree remove; separately observe registry and disk.'),
  T('observing','registry absent and disk absent','both observed gone','clean','Record verified cleanup; remove empty sample root where applicable.'),
  T('observing','registry present but disk absent','stale registry','retry','Prune Git worktree registry; then re-observe.'),
  T('observing','remaining resource or observation failed','attempts remain','retry','Retry at bounded 150ms/300ms delays; registry observation failure treated as present.'),
  T('observing','remaining resource after three attempts','cleanup not established','degraded','Attach leak path/branch and reason; do not silently report absence.','Some filesystem stat errors are treated as absent; registry verification reduces but does not eliminate uncertainty.'),
  T('cleanup requested','delete sample branch','branch expected disposable','observing','Delete branch then verify ref absence separately; retain successful task branch by policy.')
  ])

M('S31','Farm receipt publication and durable-output recovery boundary',
  'In-memory run report; tier-one run JSON/Markdown; tier-two latest copies; stream file; temp path/rename retry state.',
  'unwritten;temporary written;fsynced;renaming;JSON committed;Markdown committed;latest attempted;receipt failed',
  [FARM+'farm.ts|atomic report writes and final report|2800-3697'],[
  T('unwritten','write tier-one JSON','report constructed','temporary written','Create exclusive temporary file, preserve prior file mode, write exact bytes.'),
  T('temporary written','fsync succeeds','file complete','fsynced','Flush file; proceed to rename.'),
  T('fsynced','rename','target replacement eligible','JSON committed','Retry transient rename up to four attempts.','No directory fsync is performed; failure leaves prior target or partial publication state.'),
  T('JSON committed','write Markdown','separate atomic file transaction','Markdown committed','Publish human-readable run report after JSON.'),
  T('Markdown committed','write latest/diffs','convenience copies','latest attempted','Best-effort latest files and raw patch evidence; failures logged but do not invalidate tier-one receipts.'),
  T('any tier-one phase','write/fsync/rename failure','may follow successful task commit and merge','receipt failed','Return publication failure, potentially with JSON committed but Markdown missing.','Recover reports from durable run refs/evidence; author rerun is a different operation with destructive branch reset.')
  ])

M('S32','Farm canary provider qualification',
  'Frozen base commit; candidate provider list; entitlement/probe result; isolated per-candidate task worktree; score ordering and cleanup state.',
  'base frozen;entitlement probing;candidate admitted;candidate executing;ranked;no recommendation;reported',
  [FARM+'farm.ts|canary flow|900-1800;3300-3697'],[
  T('start canary','resolve base','configured commit exists','base frozen','Freeze base before provider probes; do not reset integration branch.'),
  T('base frozen','minimal entitlement probes','≤35s bounded per probe','candidate admitted or excluded','Drop actual 401, screen wall-clock timeout or thrown probe error.','Real probe maps network/AbortError to status 0, which survives for real canary evaluation; survivor is not entitlement or capability success.'),
  T('candidate admitted','evaluate task','fresh mkdtemp + detached worktree','candidate executing','Run task author/check pipeline without commit/merge; preserve isolated evidence.'),
  T('candidate executing','finally','candidate settled','cleanup checked','Verify worktree/branch/root cleanup before recommendation.'),
  T('all evaluated','rank','candidate outcomes known','ranked','Rank green first, then attempt count/time; one observed candidate run is not a statistical pass-rate estimate.'),
  T('ranked','cleanup degraded or no green','any leak or no successful candidate','no recommendation','Do not recommend a provider despite green work if isolation cleanup is unverified; exit 2.'),
  T('ranked','green candidate and clean resources','report writes succeed','reported exit 0','Publish bounded canary recommendation and provenance.')
  ])

M('S33','Farm safe file materialization',
  'Pinned ancestor/target handles; expected inode/link identity; desired bytes; write/close status.',
  'unresolved path;ancestors checked;target opened;revalidated;written;unsafe/partial',
  [FARM+'worktree-fs.ts|writeWorktreeFile and safety checks|1-194'],[
  T('unresolved path','write worker file','portable relative path inside worktree','ancestors checked','Create/check ancestors without following unsafe symlink boundaries.'),
  T('ancestors checked','open target','exclusive/no-follow and regular single-link target','target opened','Pin target handle and inode identity.'),
  T('target opened','pre-write revalidation','path/handle still same after optional test hook','revalidated','Reject link or replacement races before truncation.'),
  T('revalidated','write bytes','owned safe target','written','Truncate/write exact requested bytes; close handle best effort.'),
  T('any phase','unsafe identity or I/O failure','guard/write fails','unsafe/partial','Throw bounded UnsafeWorktreeWrite failure.','Write failure after truncation can leave partial bytes; caller escalates rather than presenting atomic file replacement.')
  ])

WG='core/pysrc/_workgithub.py'
M('S34','GitHub work issue creation and issue-state delivery',
  'Native work binding/config generation; staged effect; external-effect claim and attempt ID; issue marker and remote observed state; own credential source.',
  'pending create/status;conflict;outcome_unknown;remote applied;synced;binding changed',
  [WG+'|sync, verified bindings/merge/issue helpers|185-550'],[
  T('pending create/status','sync','origin/config/binding generations exact; owning credential available; endpoint allowed','validated','Re-read current config and effect; require exact mapped desired state.'),
  T('pending status','baseline observation','remote issue differs from staged expected baseline','conflict','Record conflict before claiming/sending; do not overwrite external change.'),
  T('validated','after_merge effect','verified merged PR/default path/intent/current binding and local ancestry','eligible','Require actual merge evidence, not a prose assertion or closed PR alone.'),
  T('eligible or validated','claim external effect','native revision/operation claim succeeds','outcome_unknown','Persist attempt claim as outcome_unknown before POST/PATCH; recheck binding afterward.'),
  T('outcome_unknown','send create/status','claim still current','remote applied or unknown','POST issue with stable work marker, or PATCH desired state only if needed.'),
  T('remote applied or unknown','GET readback','exact repository/issue identity, single work marker, desired state','synced','Record observation against claim revision/attempt ID.'),
  T('outcome_unknown','network/error/lost response/binding drift','effect may have happened','outcome_unknown or binding changed','Preserve uncertainty; fail explicit operation.','Never blind-repeat create/PATCH just because response failed; use target-specific reconciliation.')
  ])

M('S35','GitHub issue adoption and reconciliation',
  'Pending/unknown issue effect; supplied issue number; stable work marker; remote state; accept_remote option.',
  'create unknown;status unknown;unbound;observed;synced;conflict;refused',
  [WG+'|reconcile_issue, adopt_issue, reconcile_status|551-615'],[
  T('create unknown','reconcile supplied issue number','exact identity/single work marker','observed then synced','GET only, verify issue, record result under outstanding attempt.','No replacement POST is issued.'),
  T('unbound or pending create','adopt issue','adoption allowed; issue marker/identity verified','synced','Bind existing issue without create; native state validates adoption preconditions.'),
  T('status unknown','reconcile status','remote desired state','synced','GET and record acknowledgment; no PATCH.'),
  T('status unknown','reconcile status','remote differs and accept_remote=false','refused/unknown','Return mismatch; preserve intended effect for explicit decision.'),
  T('status unknown','reconcile status with accept_remote','verified differing remote state','conflict','Record external observation as conflict; do not silently accept intended status as delivered.')
  ])

M('S36','GitHub project item membership delivery',
  'Project/issue binding and generation; paginated remote item search; external-effect claim; current item ID.',
  'pending project add;claim unknown;item absent;item present;synced;conflict/unknown',
  [WG+'|project discovery, _find_project_item, sync_project, reconcile_project|616-904'],[
  T('pending project add','discover/search','verified project and issue configuration','item absent or item present','Read paginated project items, bounded to 3,000; verify selected issue identity.'),
  T('pending project add','claim','native coordination ready','claim unknown','Persist outcome_unknown before GraphQL mutation; recheck configuration/binding.'),
  T('claim unknown','item absent','same current claim','item present or unknown','Add item idempotently using exact issue/project IDs.'),
  T('claim unknown','item already present','identity verified','item present','Skip duplicate add mutation.'),
  T('item present','readback','remote item matches issue/project','synced','Record item ID and acknowledgment against attempt.'),
  T('claim unknown','reconcile','remote membership can be observed','synced or claim unknown','Search first; if absent, replay idempotent add then re-observe.','This retry policy differs deliberately from non-idempotent issue creation.'),
  T('any','pagination/identity/API failure','observation incomplete','conflict/unknown','Stop without calling incomplete search proof of absence.')
  ])

M('S37','GitHub project single-select field staging, CAS and recovery',
  'Field/option mapping; baseline option; desired option; work revision/binding generation; unknown attempt; remote observed option.',
  'unstaged;synced/conflict;pending field;outcome_unknown;synced;conflict',
  [WG+'|project_fields, stage_project_field, sync_project_field, reconcile_project_field|728-830;905-1045;1157-1209'],[
  T('unstaged or synchronized/conflicted','stage field intent','allowed native work state; exact field/option IDs and current baseline','pending field','Resolve remote field/option and read baseline; stage native effect with operation ID.'),
  T('pending field','sync','remote observed equals baseline or desired','eligible','Compare against baseline before writing; validate after_merge and mapped binding where required.'),
  T('pending field','remote differs from baseline and desired','external edit detected','conflict','Record external value and refuse overwrite.'),
  T('eligible','claim effect','native revision succeeds','outcome_unknown','Persist unknown attempt, recheck current bindings, write desired option only when not already desired.'),
  T('outcome_unknown','readback desired','same item/field identity','synced','Record observed option and attempt acknowledgment.'),
  T('outcome_unknown','reconcile desired','GET proves desired','synced','Record without mutation.'),
  T('outcome_unknown','reconcile baseline','baseline still matches and mapping still valid','outcome_unknown then synced','Replay desired idempotent field value, re-read and record.'),
  T('outcome_unknown','reconcile other value','neither expected nor desired','conflict','Record competing remote edit; do not overwrite.'),
  T('any send/readback','transport/identity/binding error','incomplete observation','outcome_unknown or refused','Retain unknown claim; no fabricated synchronization.')
  ])

M('S38','GitHub mapped multi-target synchronization and PR observation',
  'Per-target issue state/project membership/project field effects; coordination generation; desired map; observed PR identity/state.',
  'waiting binding;resume needed;reconcile needed;partially synchronized;complete;failed target;PR observed',
  [WG+'|sync_mapped, _resume_mapped, _verify_synchronized_mapped, observe_pull|1046-1279'],[
  T('mapped work','sync all','current map/config','per-target processing','Process issue and project effects independently; choose resume/reconcile/send/observe according to each target state.'),
  T('target','binding incomplete','required identity missing','waiting binding','Return waiting reason; do not invent remote target.'),
  T('target unknown','mapped resume','prior claim exists','reconcile needed','Dispatch target-specific observation/replay policy instead of generic resend.'),
  T('one target','failure','API/native/identity error','failed target with others continuing','Collect target error and continue independent targets; no distributed rollback.'),
  T('all targets','aggregate','all requested complete, others not_requested','complete','ok=true only if required targets complete; otherwise partial outcome retained.'),
  T('any work','observe PR','GET PR/files/head identity verifies exact work intent','PR observed','Record open/closed/merged observation through native state.','A merged PR observation does not automatically mark local work done; transition policy remains elsewhere.')
  ])

TB='core/pysrc/_taskboardlib.py'
M('S39','Legacy task board transitions and identity-preserving edits',
  'Markdown task markers, optional IDs/origin metadata, start/done dates, section position; pure text transform (I/O belongs to work adapters).',
  'queued;in_progress;done;reopened;invalid/ambiguous',
  [TB+'|add_entry, transition_error, set_state, edit_work_entry|679-804;974-1166'],[
  T('absent','add entry','valid description/origin and optional ID rules','queued','Insert queued row in selected section; optional ID minted under actual current board sequence.'),
  T('queued','set in_progress','unique target/origin; optional assigned ID valid','in_progress','Change marker, stamp start date, preserve origin/identity.'),
  T('in_progress','set done','unique target','done','Change marker, stamp done date, remove old start stamp as implemented.'),
  T('queued','set done','origin selector provided','done','Origin-selected path permits direct completion; preserve identity.','Without origin selector, queued→done is rejected; do not flatten these adapter-specific semantics.'),
  T('done','set done','already complete','done','No-op, preserve bytes/identity.'),
  T('in_progress','set in_progress','already started','same or explicit transition error','No new semantic progress; transition_error rejects invalid repeated operation where caller uses it.'),
  T('done','set in_progress','ordinary set_state API','refused','Reject implicit reopen.'),
  T('done','edit action=reopen','origin uniquely selects entry','reopened/in_progress','Explicit reopen preserves identity, adds start when absent; this is separate from ordinary set_state.'),
  T('any task','rename/attach identity','unique origin and valid operation','same state','Preserve stable task identity and other metadata while editing requested field.'),
  T('any operation','duplicate/ambiguous/missing target','selector not unique','invalid/ambiguous','Raise explicit error; no arbitrary matching row is mutated.')
  ])

M('S40','Legacy board archive and interrupted-copy recovery',
  'Open board text; done archive text; task block identity by ID or raw line; cutoff and undated confirmation owned by caller.',
  'done recent;archive eligible;archive already present;archive appended;open removed;archive_pending duplicate',
  [TB+'|archive_candidates, already_archived, archive_transform|805-973'],[
  T('done task','find archive candidates','done date older than 14-day cutoff','archive eligible','Return candidate blocks; undated done tasks require separate caller handling/confirmation.'),
  T('archive eligible','transform archive','ID/raw-line not already archived','archive appended + open removed proposal','Pure transform appends done block then removes from open text; does not perform filesystem writes itself.'),
  T('archive eligible','transform archive','matching ID or raw line already in archive','open removed proposal','Deduplicate archive entry and remove residual open task.'),
  T('wrapper commit','write archive succeeds then open write interrupted','two-file operation','archive_pending duplicate','Both files can temporarily contain task.','Retry transform recognizes archive identity and removes open copy without duplicate archive; wrapper must preserve archive-first order.'),
  T('any archive','task no longer matches','stale candidate/ambiguity','refused','Do not archive a different block under stale identity.')
  ])

M('S41','Legacy task harvest, triage and advisory diff classification',
  'Candidate origins; board/archive duplicate set; questions text; harvest mode; pure board diff classification.',
  'candidate;interactive proposal;auto queued;question deferred;blocking decision pending;already promoted;diff recognized/unrecognized',
  [TB+'|promote and classification helpers|433-556;1167-1306'],[
  T('candidate','harvest interactive','interactive mode','interactive proposal','Return proposals without auto-promoting unconfirmed decisions.'),
  T('candidate','harvest auto','work item or nonblocking question; not already promoted','auto queued or question deferred','Add queued work/origin or deferrable question; deduplicate against both board and archive.'),
  T('candidate','blocking decision','needs human decision','blocking decision pending','Escalate with explicit confirmation/audit boundary instead of treating auto mode as approval.'),
  T('candidate','duplicate origin','already on board/archive','already promoted','No duplicate entry.'),
  T('any harvest','unknown mode','unsupported string','refused','Raise ValueError before transform.'),
  T('board diff','classify','exactly one recognized queued add/start/done semantic change','diff recognized','Expose narrow bypass classification.','Archive/reopen/arbitrary edits remain unrecognized; this classifier is not the whole work lifecycle.'),
  T('board','merged task IDs observed','ID appears merged but board stale','advisory drift','Return advisory drift; do not auto-complete tasks from inference.')
  ])

RL='core/pysrc/_releaselib.py'
M('S42','Release target declaration, selection and first-adoption backfill',
  'targets file presence/parse result; declared target rows; version policy/initial version; explicit selected target; proposed backfill block.',
  'file absent;configured;malformed/empty;selection pending;selected;backfill proposal;ambiguous stop',
  [RL+'|load_targets, parse_release_targets, select_release_target*, backfill helpers|1105-1209;1986-2534;2535-2697;2822-2845'],[
  T('file absent','load targets','file truly absent','backfill eligible exit 3','Signal first-adoption path rather than invent target config.'),
  T('file exists','load targets','exact single valid block, required keys, disjoint prefixes and valid policies','configured','Parse deterministic target rows; latest-eligible target at most one.'),
  T('file exists','missing/empty/malformed/duplicate/unknown keys','invalid declaration','malformed/empty exit 4','Stop; existing invalid file does not trigger automatic backfill.'),
  T('configured','select by explicit name/confirmation','exactly one chosen declared target','selected','Return selected target contract and policy.'),
  T('configured','unknown/no/multiple selection','cannot choose uniquely','selection pending/refused','Require explicit valid target; do not infer from branch/file names.'),
  T('backfill eligible','scan top-level sources','one manifest and one changelog candidate or unambiguous supported shape','backfill proposal','Produce block using declared defaults (app-v prefix/latest eligibility and payload exclusion); no automatic file write in helper.'),
  T('backfill eligible','ambiguous candidates','multiple plausible manifest/changelog sources','ambiguous stop','Return precise candidates; no arbitrary selection.')
  ])

M('S43','Release baseline, change-window and version derivation gates',
  'Selected version policy; tag set/highest policy-compliant version; ancestor verification; conventional commit window; reconciliation ledger and published SHA set.',
  'baseline unresolved;baseline verified;change window classified;footer missing;bump derived;nonbumping;refused',
  [RL+'|last_tag_select*, verify_tag_ancestor, classify_commit/window, reconciliation, derive_version|554-849;1269-1744;1745-1821'],[
  T('baseline unresolved','select last tag','matching target prefix and policy','candidate baseline','Choose highest version, not first lexical or newest timestamp.'),
  T('candidate baseline','verify ancestry','tag resolves and is ancestor of candidate','baseline verified','Use that baseline for exact change window.'),
  T('candidate baseline','not ancestor/unresolvable','highest candidate invalid','refused','Do not silently select an older tag to make release proceed.'),
  T('baseline verified','classify window','exact commits and terminal footer assertions','change window classified','Conventional commit bump precedence major > minor > patch; only terminal paragraph footer parsed as release assertion.'),
  T('change window classified','bumping commit lacks required footer','no eligible published-SHA reconciliation','footer missing exit 1','Refuse release derivation until provenance obligation resolved.'),
  T('change window classified','reconciliation eligible','exact published SHA ledger supplies missing assertion','change window classified','Fill missing footer evidence only; do not change bump type.'),
  T('change window classified','no bumping payload changes','all nonbumping','nonbumping exit 2','No release version manufactured.'),
  T('change window classified','bump available','valid semver or declared numeric-sequence policy','bump derived','Apply policy-specific successor; preserve legitimate difference between semver and numeric sequence.'),
  T('no previous release','first release baseline','adoption log identifies supported baseline','baseline verified','Use first-adoption boundary, not arbitrary repository first commit.')
  ])

M('S44','Release publish classifier and exact-HEAD merge readiness',
  'Observed tag existence/SHA/version; candidate HEAD/version; published/draft release observation; exact-name check runs for exact head.',
  'fresh publish;resume publish;already published;abort mismatch;checks missing;checks pending;checks wrong head;checks failed;merge ready',
  [RL+'|classify_publish_state, classify_merge_readiness|1075-1104;1210-1268'],[
  T('tag absent','classify publish','no conflicting existing tag','fresh publish','Return fresh path; helper itself creates no tag/release.'),
  T('tag present','classify publish','tag SHA or version differs from candidate','abort mismatch','Abort even if a release is already published; published state does not waive identity mismatch.'),
  T('tag present matching','classify publish','release published and nondraft','already published','No publish operation needed for this classifier.'),
  T('tag present matching','classify publish','release missing/unpublished/draft','resume publish','Permit completion path under exact same tag identity; do not create another tag.'),
  T('merge readiness unknown','classify checks','no exact required name','checks missing','Return missing; similarly named checks do not qualify.'),
  T('merge readiness unknown','classify checks','any matching check on wrong SHA','checks wrong head','Refuse stale-head success.'),
  T('merge readiness unknown','classify checks','matching exact-head check incomplete','checks pending','Wait; do not infer success from another completed duplicate.'),
  T('merge readiness unknown','classify checks','any matching complete result not SUCCESS','checks failed','Refuse neutral/skipped/failure/cancelled outcomes.'),
  T('merge readiness unknown','classify checks','all matching exact-name exact-head checks complete SUCCESS','merge ready','Return readiness evidence; merger side effect remains outside helper.')
  ])

M('S45','Release notes, assets and committed-source identity',
  'Committed revision/path; parsed version/date headings; tag message dates; declared asset templates and on-disk inventory.',
  'unverified;committed notes read;notes consistent;assets complete;refused',
  [RL+'|committed changelog, section/date/asset verification|329-553;850-1074'],[
  T('unverified','read release notes','full 40/64-hex commit or explicit tag ref; normalized repository-relative path','committed notes read','Read exact regular Git blob, not uncommitted working-tree changelog.'),
  T('committed notes read','validate section','exact selected version/policy heading and supported schema','notes consistent','Extract selected section; compare release/tag date assertions.'),
  T('unverified assets','render asset templates','safe portable nonempty unique names','expected inventory','Bind asset names to selected version/tag.'),
  T('expected inventory','verify assets','exact declared inventory; each bounded/nonempty regular file as required','assets complete','Return verified inventory for caller publication.'),
  T('any verification','missing/extra/empty/linked/invalid note/date/path','guard fails','refused','Stop before publication; no permissive filename-based guess.')
  ])

M('S46','Release pre-tag command runner and tree cleanliness',
  'Ordered command cursor; baseline tracked/untracked/index content snapshot; governance-scratch exclusions; subprocess exit code; after-command snapshot.',
  'snapshot pending;command running;command failed;could not run;tree changed;probe failed;next command;passed',
  [RL+'|pre-tag command CLI, shell resolution, governance_scratch_exclusions, release_tree_status|1822-1985;2105-2259;2846-4229'],[
  T('snapshot pending','begin pre-tag checks','valid target and non-overlapping governance scratch exclusions','command running','Snapshot tracked/untracked/index bytes/hashes excluding only admitted scratch; run ordered command via supported shell.'),
  T('command running','nonzero exit','ordinary failure','command failed exit 5','Stop at first failed command.','No after-command hash check on this branch; failing command may have changed tree; no rollback is attempted.'),
  T('command running','launch unavailable','126/127/9009 class','could not run exit 7','Report command could not run, distinct from test failure.'),
  T('shell resolution','Windows no POSIX shell','configured shell unavailable','could not run exit 9','Refuse rather than reinterpret shell syntax.'),
  T('command running','zero exit','command completed','snapshot after command','Re-observe tracked/untracked/index content, not just git status.'),
  T('snapshot after command','content/index changed','outside admitted scratch','tree changed exit 6','Stop; retain actual modified tree for user inspection, no automatic reset.'),
  T('snapshot after command','probe unavailable','cannot establish tree equivalence','probe failed exit 8','Do not classify unknown as clean.'),
  T('snapshot after command','same tree','commands remain','next command then running','Advance ordered cursor.'),
  T('snapshot after command','same tree','last command passed','passed','Return successful pre-tag gate.','Commands themselves have no explicit runtime bound; Git helper probes use 30-second timeout.')
  ])

M('S47','Sandbox Docker client request lifecycle',
  'Spawned Docker CLI process; first terminal reason; deadline/abort signal; bounded stdout/stderr buffers; settled flag.',
  'not spawned;running;timeout latched;abort latched;overflow latched;closed',
  [SB+'docker.ts|runDocker bounded subprocess|1-327'],[
  T('not spawned','Docker call','signal already aborted','closed code 130','Return cancellation without starting client.'),
  T('not spawned','Docker call','admitted args/environment','running','Spawn Docker CLI; capture output under default 64MiB cap (exec supplies 256MiB).'),
  T('running','deadline elapsed','first failure reason','timeout latched','SIGKILL Docker client; report 124/timedOut.'),
  T('running','abort signal','first failure reason','abort latched','SIGKILL Docker client; report 130/aborted.'),
  T('running','output bound exceeded','first failure reason','overflow latched','SIGKILL Docker client; report ordinary exit 1 with bounded error.','No distinct overflow bit reaches exec cleanup policy; killing CLI does not prove container workload stopped.'),
  T('running','spawn error/normal close','no prior failure','closed','Return ordinary exit code/error; settle exactly once and remove timers/listeners.'),
  T('latched failure','close','reason already chosen','closed','Preserve first reason rather than overwrite with close status; return retained bounded output.')
  ])

M('S48','Sandbox create and compensation sequence',
  'Sandbox name/labels, source volume, clone-helper/container IDs, temporary host checkout, image identity, runtime container; cleanup attempts.',
  'validated;volume created;cloning;checkout copied;image built;container created;ready;cleanup attempted;unknown residue',
  [SB+'create.ts|createSandbox and defaultBuildImage|1-480',SB+'run.ts|runtime container plan|1-219',SB+'mounts.ts|mount boundary|1-157'],[
  T('validated','create source volume','safe name/source/mount policy','volume created','Create labeled volume before clone/build operation try block.','An uncertain volume-create result before the try has no compensation path.'),
  T('volume created','clone source','source clone admitted','cloning','Start network-capable clone helper writing only managed source volume.'),
  T('cloning','clone finishes','Git clone success','checkout copied','Copy volume checkout into a newly named host temp directory for build analysis.'),
  T('checkout copied','build image','build helper returns image','image built','Resolve dependency image/cache and build; remove temporary host checkout in finally.'),
  T('image built','run sandbox','labels/workdir/env/mount plan valid','container created then ready','Start ordinary runtime container on offline network policy; source volume mounted at workspace.'),
  T('any post-volume phase','failure','resource may have been created','cleanup attempted','Attempt container removal then source volume removal; rethrow original error.'),
  T('cleanup attempted','remove command fails or cancelled','cleanup exit result ignored','unknown residue','Original error remains; resource absence is not verified.','Compensation should return residual resource identities/unknown status, not silently discard them.'),
  T('cloning/building','caller abort','default clone/build lacks propagated AbortSignal','same phase until helper ends','Cancellation reaches later Docker/runtime stages, but host clone/build may continue.','Do not claim immediate whole-create cancellation from CLI abort alone.')
  ])

M('S49','Sandbox dependency-image cache and build fallback',
  'Dependency-file hash, image tag from checkout basename, optional Nixpacks tool identity, cached-image inspect, generated Dockerfile/dependency context, temp helper.',
  'hash computed;cache hit;cache miss;Nixpacks attempt;fallback plan;building;built;failed;cleanup pending',
  [SB+'dephash.ts|computeDepHash|1-86',SB+'build.ts|imageTag/buildImage and fallback|1-616',SB+'create.ts|defaultBuildImage|1-480'],[
  T('checkout ready','compute dependency hash','declared lock/config inputs readable','hash computed','Hash supported dependency files; optional tool-version input exists in helper.'),
  T('hash computed','choose image tag','current host checkout path','cache lookup','Tag incorporates checkout basename plus dependency hash.','Create supplies random temp basename, so equal dependencies across creates receive different tags; nixpacksVersion is not passed into current hash call.'),
  T('cache lookup','docker image inspect exits 0','tag exists','cache hit','Reuse image without rebuild.'),
  T('cache lookup','inspect nonzero','missing image OR Docker read failure','cache miss','Proceed to rebuild.','Daemon/unavailable observation is collapsed into cache miss rather than distinct unknown.'),
  T('cache miss','Nixpacks available','host/WSL platform routing eligible','Nixpacks attempt','Generate build plan with Nixpacks.'),
  T('Nixpacks attempt','unsupported/unavailable/failure','fallback supported','fallback plan','Use built-in Node/Python dependency plan according to discovered project shape; otherwise fail explicitly.'),
  T('plan ready','docker build','generated Dockerfile/context ready','building','Write build context and dependency files; run build under helper-specific command behavior.'),
  T('building','build success','image emitted','built','Return exact tag; remove helper-generated files/temp context.'),
  T('any build','finally','temporary helper exists','cleanup pending','Spawn synchronous Docker removal/host cleanup.','Some spawnSync cleanup has no explicit timeout/AbortSignal; cleanup can outlive cancellation or hang.')
  ])

M('S50','Sandbox network policy planning and enforcement',
  'Requested policy, Docker network choice/capabilities, DNS-resolved allowlist IPs, iptables commands, temporary clone connectivity.',
  'offline plan;clone bridge;allowlist configuring;allowlist enforced;failed configuration;detached',
  [SB+'network.ts|network planner/firewall installation|1-272',SB+'run.ts|NETWORKED_POLICIES and runtime planning|1-219',SB+'cli.ts|network option handling|1-496'],[
  T('runtime plan','ordinary run/create','current NETWORKED_POLICIES set empty','offline plan','All ordinary sandbox runtime containers use --network none.'),
  T('clone helper','clone phase','temporary source acquisition allowed','clone bridge','Use temporary bridge network; disconnect after clone before handing off runtime state.'),
  T('standalone network helper','egress-allowlist request','supported helper caller; NET_ADMIN; explicit hosts','allowlist configuring','Resolve permitted names, configure DNS and iptables allow rules, set default-drop last.'),
  T('allowlist configuring','all commands succeed','required resolution and firewall setup complete','allowlist enforced','Container may reach only admitted destinations according to helper policy.'),
  T('allowlist configuring','resolution/firewall failure','before final default-drop may occur','failed configuration','Return failure; caller must destroy or otherwise contain container.','Helper existence does not mean ordinary CLI allowlist flag is wired to it; current run integration remains offline.'),
  T('clone bridge','disconnect','clone complete','detached','Remove temporary connectivity; verify via command result where caller implements check.')
  ])

M('S51','Sandbox Claude-inside admission, network firewall and teardown',
  'Dedicated Claude home volume, auth environment, no source mount, container ID, requested offline/Anthropic policy, firewall result and cleanup attempt.',
  'preflight;home prepared;container running;firewall pending;ready;failed cleanup;stopped',
  [SB+'claude-inside.ts|createClaudeInside and cleanup|1-399',SB+'claude-inside-cli.ts|CLI workflow|1-220'],[
  T('preflight','launch Claude-inside','token from allowed environment; safe config; caller owns home volume','home prepared','Create/use dedicated home volume; do not copy host auth files or mount repository source.'),
  T('home prepared','docker run','offline or explicit Anthropic policy','container running','Start isolated container with scoped auth env and home volume.'),
  T('container running','networked policy','requires root firewall setup','firewall pending','Install allowlist rules inside container.'),
  T('firewall pending','firewall succeeds','all expected commands zero','ready','Return usable container identity.'),
  T('firewall pending','firewall fails','container exists','failed cleanup','Attempt docker rm -f using normalCall, which inherits potentially aborted signal; ignore removal status, then throw message saying container destroyed.','Actual destruction is not established; preserve unknown cleanup and re-observe with un-aborted cleanup channel.'),
  T('ready','session finishes / caller destroy','caller-directed cleanup','stopped or unknown','Stop/remove container; home-volume lifecycle belongs to caller, not implicit source checkout cleanup.')
  ])

M('S52','Sandbox exec and copy side effects',
  'Container selection by labels; Docker exec result, timeout/abort flags; stop result; copy source/destination and host partial output.',
  'selected;executing;completed;command failed;interrupted;stopping;stopped;stop failed;copy partial',
  [SB+'exec.ts|execInSandbox|1-208',SB+'cp.ts|copy files|1-110'],[
  T('selected','exec','target selected and args valid','executing','Run command with bounded output and caller signal; host client controls observation, container owns workload.'),
  T('executing','ordinary exit zero/nonzero','no timedOut/aborted flag','completed or command failed','Return exit/output and leave container running.'),
  T('executing','timeout or abort','result timedOut/aborted','interrupted then stopping','Issue docker stop --time 0 via cleanup call without aborted caller signal.'),
  T('stopping','stop result','zero or failure','stopped or stop failed','Return original command outcome plus explicit stop outcome; do not replace original reason.'),
  T('executing','Docker client output overflow','docker helper returns ordinary exit 1','command failed','Current path returns without docker stop.','Confirmed fake-Docker probe: overflow called exec only, not stop; container workload may continue unseen.'),
  T('selected','copy','safe explicit source/destination','completed or copy partial','Invoke docker cp; host output may be partially created if interrupted/error.','No transactional host-file rollback or partial-copy recovery metadata is provided.')
  ])

M('S53','Sandbox resource discovery, destroy and prune verification',
  'Docker label-filtered container/volume observations; explicit target set; keep-volume option; per-resource failure records; final re-list.',
  'discovery;targets known;discovery unknown;removing;verifying;clean;residual resources',
  [SB+'registry.ts|list/find registry views|1-242',SB+'destroy.ts|destroy/prune lifecycle|1-381'],[
  T('registry display','list containers/volumes','Docker list command fails','empty display','Read-view helper returns empty list on failure.','Empty output here is not proof that no sandbox resources exist; isolated probe confirms failure→[].'),
  T('destroy/prune','discover targets','Docker list exit success and labels valid','targets known','Freeze observed target identities; honor keep-volume selection.'),
  T('destroy/prune','discover targets','list failed/unparseable','discovery unknown','Return/record failure instead of treating target set as empty.'),
  T('targets known','remove','all targeted containers then volumes','removing','Attempt every target even when an earlier removal fails; retain bounded failure report (25 details with distinct total count).'),
  T('removing','re-list','removal attempts complete','verifying','Observe target identity absence, not merely successful rm return.'),
  T('verifying','all targeted resources absent','list successful','clean','Report cleanup success; new concurrent untargeted resources do not retroactively fail this operation.'),
  T('verifying','targets remain or observation fails','cannot prove absence','residual resources','Report remaining IDs and observation failure.','Retry addresses remaining known targets; keep-volume resources are intentionally excluded, not leaks.')
  ])

M('S54','Sandbox CLI cancellation and command outcome mapping',
  'Parsed subcommand/options; AbortController; SIGINT count; interrupted flag; async command result/exception.',
  'parsing;running;interrupt requested;forced exit;resolved;failed',
  [SB+'cli.ts|CLI dispatcher and interrupt handling|1-496',SB+'claude-inside-cli.ts|separate CLI|1-220',SB+'docker-gate.ts|test dependency admission|1-180'],[
  T('parsing','valid create/shell/exec/cp/destroy/prune','command-specific options valid','running','Dispatch one selected operation and install interrupt handler.'),
  T('running','first SIGINT','not already interrupted','interrupt requested','Abort shared controller; request cooperative cleanup.'),
  T('interrupt requested','second SIGINT','already interrupted','forced exit 130','Exit immediately; cleanup may not finish.'),
  T('running or interrupted','promise resolves','interrupted flag true','resolved exit 130','Override normal command exit to cancellation.'),
  T('running or interrupted','promise throws','exception path','failed exit 1','Catch currently maps exception to 1 even after abort.','Keep interrupt intent and operation failure separate when normalizing result semantics.'),
  T('test gate only','Docker admission','required CI flag + usable Linux Docker','test admitted or hard failure','Required test mode throws on unavailable/incompatible Docker; local nonrequired mode may skip.','This is a test execution gate, not production sandbox enablement.')
  ])

SC='site/src/components/'
SS='site/src/scripts/'
M('S55','Site search loading, query generations and result expansion',
  'Cached Pagefind loader promise; query generation token; debounce timer; results/all-results mode; active option; dialog/focus state.',
  'idle;loading index;index ready;load error;search pending;results;empty;show-all pending;closed/disconnected',
  [SC+'Search.astro|custom search component|1-650'],[
  T('idle','focus or nonempty query','component connected','loading index','Lazy load Pagefind; reuse pending promise.'),
  T('loading index','module loads','current component','index ready','Cache module and enable query.'),
  T('loading index','import fails','loader catch','load error','Display retry path; failed promise stays cached until explicit force reload/cache bust.'),
  T('load error','retry','user activates retry','loading index','Clear loader cache and retry import.'),
  T('index ready/results','input','nonempty normalized query','search pending','Debounce 140ms; increment generation; run Pagefind search and fetch result data; default first eight.'),
  T('search pending','results resolve','generation still newest','results or empty','Paint current results, count/active selection; ignore stale completions.'),
  T('search pending','search/results.data rejects','runtime search failure','stale prior display/unhandled rejection','Only module loading is caught; result-query promises have no equivalent error/retry state.','Add bounded explicit search error to avoid leaving stale results as current.'),
  T('results','show all','more than default page','show-all pending','Disable expansion button while awaiting all result data.'),
  T('show-all pending','data succeeds/fails','newest query','all results or disabled stale display','Success renders all; rejection lacks catch/finally and can leave button disabled.'),
  T('results','arrow/Enter/submit','results exist','results/navigation','Wrap active option; Enter/click follows selected result; Ctrl/Cmd+K focuses search.'),
  T('any','empty query/Escape/outside/disconnect','close condition','closed/disconnected','Clear debounce, increment token, close results and invalidate pending response; remove owned listeners.')
  ])

M('S56','Academy local bookmark and cross-tab state',
  'Base-scoped localStorage v1 key containing exact release/commit/lesson identity; connected listeners; storage availability.',
  'empty;ready;invalid;stale;storage unavailable;saved;cleared;disconnected',
  [SS+'academy-bookmark.ts|bookmark load/save validation|1-61',SC+'AcademyBookmark.astro|bookmark UI lifecycle|1-250'],[
  T('connect','read stored bookmark','valid exact schema/release/commit/lesson','ready','Render continue link for declared current lesson.'),
  T('connect/read','no key','read succeeded','empty','Show save/start state; do not infer progress.'),
  T('connect/read','malformed/other release or commit/unknown lesson','stored data not current','invalid or stale','Show reset/restart option rather than silently navigate to arbitrary stale data.'),
  T('any bookmark UI','storage read/write throws','browser storage denied/unavailable','storage unavailable','Render unavailable state; distinguish from empty bookmark.'),
  T('ready/empty','explicit save','valid current lesson identity','saved','Write only scoped bookmark key; update display.'),
  T('saved/stale/invalid','clear','explicit user action','cleared','Remove only owned key; preserve unrelated browser data.'),
  T('connected','storage event/pageshow','external tab/history changed state','refreshed state','Re-read owned key and validate; cross-tab state can update display.'),
  T('connected','disconnect','custom element removed','disconnected','Abort owned listeners.','Bookmark is navigation convenience, not verified training completion.')
  ])

M('S57','Academy command preferences and copy interaction',
  'OS/host choices independently unset or selected; optional storage record; visible command variants; clipboard feedback.',
  'unset;partially selected;selected;storage fallback;copy pending;copied;copy failed',
  [SS+'academy-command-preferences.ts|preference validation|1-66',SC+'AcademyCommandPreferences.astro|preference component|1-450'],[
  T('connect','read preferences','record validates','partially selected or selected','Apply separate OS and host filters; otherwise start unset.'),
  T('any choice','choose OS or host','supported option','updated selection','Update UI immediately; persist best effort; if no variants match, fall back to showing all.'),
  T('updated selection','storage write fails','browser denies storage','storage fallback','Keep current in-memory choice; no false durability claim.'),
  T('visible command','copy','clipboard API available','copy pending','Copy exact rendered command text.'),
  T('copy pending','clipboard resolves','success','copied','Display success feedback.'),
  T('copy pending','clipboard rejects','failure','copy failed','Select command text for manual copy; show failure state.'),
  T('DOM reused','setup again','dataset once-bound guard','same','Avoid duplicate binding.','No cross-tab storage listener or disconnect abort is installed by this component.')
  ])

M('S58','Site guide-directory filter',
  'Normalized query ≤160 chars, selected category, DOM result/group visibility, count/no-results state; AbortController.',
  'all visible;filtered;no matches;cleared;disconnected',
  [SS+'guide-filter.ts|filter predicates|1-12',SC+'GuideDirectory.astro|directory interaction|1-360'],[
  T('all visible or filtered','input/category change','query NFKC-normalized and bounded','filtered or no matches','Require every normalized term and selected category; update cards, empty groups, count and no-results message.'),
  T('filtered/no matches','clear','user action','cleared/all visible','Clear query/category as implemented; return focus to input.'),
  T('connected','disconnect','element removed','disconnected','Abort event listeners.','No history/network/storage effects; this is view state only.')
  ])

M('S59','Site evidence/context/example selection and Academy disclosure',
  'Selected case/example ID; aria state; hidden panels; focused tab; per-lesson disclosure state; once-bound DOM marker.',
  'default first;selected case;all cases;keyboard focus moved;details open;details closed',
  [SC+'DecisionEvidence.astro|case selection|1-500',SC+'ContextExplorer.astro|context selection|1-500',SC+'ExampleChoices.astro|tabs|1-400',SC+'AcademyOverview.astro|lesson disclosures|1-251'],[
  T('component connect','initialize','declared cases exist','default first','Select first eligible panel and synchronize aria/hidden state.'),
  T('selected case','button/case change','known case or all option','selected case or all cases','Change visible content and selected controls; no external evidence is generated.'),
  T('example tabs','Arrow/Home/End','eligible tab set','keyboard focus moved','Move focus/selection according to explicit tab ordering; update aria-selected and tab stops.'),
  T('Academy details','individual toggle/show all','lesson details exist','details open/closed','Update disclosure state and aggregate toggle aria text.'),
  T('Astro page load','setup again','dataset bound marker','same','Avoid duplicate Academy disclosure bindings.','These view choices do not alter artifact, lesson verifier or approval state.')
  ])

M('S60','Site execution-map fragment navigation',
  'Active chapter selection; current hash; target details ancestors; queued animation-frame focus/scroll; page lifecycle.',
  'default chapter;manual chapter;fragment resolving;revealed;focused;stale navigation',
  [SS+'execution-map-navigation.ts|navigation helpers|1-75',SC+'ExecutionMap.astro|map interaction|1-500'],[
  T('default/manual chapter','manual chapter click','known chapter','manual chapter','Reveal selected chapter without writing browser history.'),
  T('any map view','hashchange/popstate/page load','recognized target fragment','fragment resolving','Resolve safe target; reveal ancestor details and chapter.'),
  T('fragment resolving','animation frame','target still current/connected','focused','Scroll/focus target after layout; avoid focus on stale element.'),
  T('same fragment','link click microtask','browser may not fire hashchange','fragment resolving','Repeat navigation explicitly so current-hash links still reveal/focus target.'),
  T('pending fragment','view detached/new navigation','guard invalid','stale navigation','Discard stale queued work; no unrelated history mutation.')
  ])

M('S61','Site workflow atlas view, route, node, zoom, print and export',
  'Active view/route/node; scale [0.1,2], fit mode, drag/pointer state, reading/source dialog; navigation revision/pending link; print backup; object URLs; AbortController.',
  'connected;view loaded;route selected;node inspected;manual viewport;fit viewport;source dialog;printing;export pending;disconnected',
  [SS+'workflow-atlas.ts|custom atlas runtime|1-565',SC+'WorkflowAtlas.astro|atlas DOM contract|1-600'],[
  T('connect/reconnect','setup','valid rendered atlas structure','connected/view loaded','Abort prior listeners, register current lifecycle; clone selected pristine SVG and initialize controls.'),
  T('view loaded','switch view','known view','new view loaded','Clone pristine SVG, clear selected node, reset fit; preserve eligible route selection.'),
  T('view loaded','choose route','known route','route selected','Highlight route; clear node inspection; update accessible route description.'),
  T('view loaded/route selected','select node','node metadata available','node inspected','Show source/evidence/description panel and aria selection.'),
  T('any viewport','zoom/drag','scale clamp 0.1..2; admitted pointer','manual viewport','Update transform; capture/release pointer; manual mode suppresses automatic fit.'),
  T('any viewport','fit width/all','container geometry available','fit viewport','Calculate viewport scale/translation; resize schedules coalesced recompute only outside manual/printing modes.'),
  T('any view','fragment route/node link','safe known alias/fragment','navigation pending','Advance navigation revision, switch relevant view and defer focus/scroll.'),
  T('navigation pending','animation frame','same revision; not repeated already-followed link','view selected/focused','Apply final selection/focus; older revisions are dropped.'),
  T('node inspected','open source dialog','source metadata present','source dialog','Open dialog; maintain focus and close controls.'),
  T('any view','beforeprint','not already printing','printing','Save interactive state, reveal print-relevant view/details and fit for print.'),
  T('printing','afterprint/disconnect','print backup exists','restored interactive state','Restore previous selections/details/viewport and clear backup.'),
  T('view loaded','export SVG','pristine selected SVG available','export pending','Create downloadable Blob URL from pristine SVG, trigger download, revoke URL after 1s.'),
  T('connected','disconnect','component removed','disconnected','Abort listeners, restore print state, release pointer, close dialog, revoke owned URLs and invalidate navigation work.')
  ])

M('S62','Site splash documentation drawer',
  'Open flag; aria-expanded/hidden; saved inert flags and body overflow; focus return target; document Escape listener; initialized dataset.',
  'closed;opening;open;closing;disconnected;reconnected',
  [SC+'SplashDocsRail.astro|drawer setup and cleanup|1-550'],[
  T('closed','opener click','drawer connected','open','Set aria, save/apply inert and body overflow, focus drawer target, install focus trap/Escape behavior.'),
  T('open','close button/backdrop/Escape','eligible close event','closed','Restore saved inert/overflow and opener focus; update aria state.'),
  T('open','Tab','focus at boundary','open','Cycle focus within drawer.'),
  T('connected','disconnect cleanup','component removed','disconnected','Remove document Escape handler and delete initialized marker.'),
  T('disconnected','reconnect same element','initialized marker removed','reconnected','Setup adds opener/close/tray handlers again.','Source inspection: local handlers were not removed in cleanup, so repeated same-element connection can duplicate toggles; not exercised in browser probe.')
  ])

M('S63','Site table-of-contents tracking and forced theme',
  'Observed headings/header position; active heading; scheduled frame; last-heading tail zone; dark theme DOM/storage setting.',
  'observing;update queued;active heading;bottom last heading;disconnected;dark applied',
  [SC+'TableOfContents.astro|heading tracking|1-400',SC+'ThemeProvider.astro|theme application|1-100'],[
  T('observing','scroll/resize/layout change','component connected','update queued','Coalesce tracking in requestAnimationFrame; account for header offset.'),
  T('update queued','frame','current headings','active heading','Select heading based on actual scroll position and update active link.'),
  T('update queued','near document bottom','virtual tail region','bottom last heading','Keep final heading active when there is insufficient scroll space beneath it.'),
  T('observing','disconnect','component removed','disconnected','Remove owned observers/listeners and pending frame.'),
  T('document setup','theme provider executes','any stored/system preference','dark applied','Force dark DOM theme and persist best effort.','This surface has no independent user light/dark selection lifecycle.')
  ])

M('S64','Site reference-generation pipeline and partial output',
  'Capture freshness status; in-memory source/catalog/curation model; generated output tree; ordered generator stage cursor.',
  'preflight;models built;reference replacement;later pages generating;complete;partial output',
  ['site/scripts/gen.ts|main generation order|1-134','site/scripts/generator/generate.ts|generateReference|1-479'],[
  T('preflight','generate site sources','capture inventory nonempty and all recorded source hashes current','models built','Validate captures before reference generation; collect/parse/curate command/catalog/host availability/skill pairs in memory.'),
  T('models built','render reference','all models admitted','reference replacement','Render expected reference files; clean generated command/skill/agent/lens/index destinations before writing new files.'),
  T('reference replacement','writes complete','no I/O/render error','later pages generating','Generate hook/config/changelog pages, then Academy source/topic map/pages, then release applicability.'),
  T('later pages generating','all stages finish','all required output produced','complete','Return build success.'),
  T('replacement or later stage','I/O/parser/render error','earlier stages may have written/deleted outputs','partial output','Throw and fail build without whole-output-tree rollback.','Rerun from fixed source rebuilds output; failed generation is not an atomic artifact publish.')
  ])

M('S65','Site Pagefind index build and staged replacement',
  'Pagefind service/index; added page count; in-memory emitted bundle; staged temp directory; prior pagefind output directory.',
  'indexing;bundle collected;validated;staged;old removed;renamed;failed',
  ['site/scripts/pagefind-build.ts|buildPagefind|1-119','site/astro.config.mjs|astro build done integration|1-231'],[
  T('build done','create Pagefind index','output directory available','indexing','Create service index, add built directory; require positive indexed page count.'),
  T('indexing','getFiles','service succeeds','bundle collected','Copy owned emitted bytes in memory; always close service in finally.'),
  T('bundle collected','validate bundle','portable unique names; nonempty bytes; valid entry JS and JSON','validated','Reject malformed/empty generated index before touching prior output.'),
  T('validated','stage bundle','fresh temp directory','staged','Write files exclusively; re-read and hash to prove exact staged bytes.'),
  T('staged','replace output','staged validation succeeded','old removed','Remove prior pagefind directory.'),
  T('old removed','rename temp','rename succeeds','renamed','Install staged index; cleanup temp leftovers in finally.'),
  T('any before removal','failure','service/validation/stage error','failed','Prior output remains; close service and remove temp.'),
  T('old removed','rename failure','old directory already deleted','failed with missing index','Build fails and old index is gone.','This is build-directory replacement, not live deployment atomicity; use backup/rename swap if preservation is required.')
  ])

M('S66','Site evidence capture, cleanup and freshness gate',
  'Declared capture targets; fresh fixture directory; Python process result and loaded-module hashes; normalized artifact bytes; existing capture directory.',
  'old captures pruning;fixture ready;entry running;capture validated;written;fixture disposed;freshness verified;failed partial',
  ['site/scripts/capture/run.ts|capture runner|1-40','site/scripts/capture/harness.ts|captureOne and process|1-191','site/scripts/capture/verify.ts|freshness verification|1-155'],[
  T('start capture','prune obsolete','target inventory known','old captures pruning','Remove captures no longer declared before new capture generation.'),
  T('per target','create fixture','isolated fixture setup succeeds','fixture ready','Create deterministic test repository/context for concrete tool behavior.'),
  T('fixture ready','run Python entry','available interpreter','entry running','Run with 60s bound; only ENOENT selects alternate Python interpreter; collect imported module paths/hashes and output.'),
  T('entry running','result received','expected exit, nonempty normalized output, no fixture-path leak','capture validated','Record concrete output plus source/module digests.'),
  T('capture validated','compare/write','bytes differ from stored artifact','written','Write changed capture only; unchanged bytes retained.'),
  T('per target any phase','finally','fixture acquired','fixture disposed','Always dispose fixture resource.'),
  T('all targets','freshness check','nonempty records, safe paths, tool included, each recorded hash matches current source','freshness verified','Then generate hook proof.'),
  T('any phase','execution/validation/write/freshness failure','earlier captures may already be updated','failed partial','Fail pipeline; no whole-directory transaction or restoration of obsolete captures.')
  ])

M('S67','Academy source admission and generated-course replacement',
  'Declared Academy release; submodule path/current Git HEAD; validated track/lesson inventory; setup installer digest tokens; parsed guides/actions/metadata; output tree.',
  'source unresolved;source admitted;guides parsed;coverage validated;old output removed;generated;partial output',
  ['site/scripts/academy-source.ts|loadAcademySource|1-358','site/scripts/generate-academy.ts|generateAcademy|1-324'],[
  T('source unresolved','load source','real submodule path; exact declared manifest shape/ordered IDs/three tracks; Git HEAD available','source admitted','Bind source metadata to declared release and observed commit; require home guide and ordered setup actions.'),
  T('source admitted','validate installer references','all required SHA tokens match exact installer/checksum bytes and commit','guides parsed','Read guides/actions and parse lesson/track metadata.'),
  T('guides parsed','validate wayfinding/topic coverage','all required references/metadata present','coverage validated','Build course/track models before replacing old output.'),
  T('coverage validated','begin generation','destination admitted','old output removed','Delete Academy output root; write index, lessons, tracks, generated content and sidebar.'),
  T('old output removed','all renders/writes succeed','remaining action references valid','generated','Return current generated course.'),
  T('old output removed','late action-render/I/O failure','replacement already began','partial output','Fail with incomplete Academy tree; fix and rerun generator.'),
  T('source reads','working files differ from Git HEAD','not independently checked for every guide/action','source identity caveat','Helper records Git HEAD while reading working-tree guide/action bytes.','Do not claim all rendered content equals committed submodule bytes without separate cleanliness/pin verification; this audit did not mutate submodule to demonstrate drift.')
  ])

PK='tools/build-host-packages.py'
M('S68','Native artifact candidate build and protected qualification',
  'Native host/Go target; tests-skipped flag; binary/manifest bytes; CI source/run/job identity; optional same-run native binding and context observations.',
  'unbuilt;native tests running;unqualified candidate;native-tested candidate;qualification eligible;qualified receipt;refused',
  ['tools/build-artifacts.py|main, write_qualification, load_context_observation|1-243'],[
  T('unbuilt','build','supported native OS/architecture; offline local Go settings','native tests running','Run Go tests (30m configured gate) and vet; then reproducible-flag Go build.'),
  T('unbuilt','build --skip-tests','development cross/native build','unqualified candidate','Build binary and write release manifest with native_tested=false; cannot promote as qualified payload.'),
  T('native tests running','tests/vet/build succeed','actual host target matches selected Go target','native-tested candidate','Write binary and five-key release manifest with digest/native_tested=true.','This candidate flag alone is not protected CI qualification or upstream-host proof.'),
  T('candidate','qualify-existing','GITHUB_ACTIONS, protected job/workflow/run/SHA, checked-out HEAD exact, platform matches','qualification eligible','Read candidate identity and binary digest; bind native host Go or explicit same-run off-host stamp.'),
  T('qualification eligible','optional context observation','exact six finite case identities, module/tool hashes, exit zero and expected subtests/source digests','qualification eligible','Attach validated context_native observation; no raw claim-only case acceptance.'),
  T('qualification eligible','write receipt','new destination in existing directory','qualified receipt','Exclusive-create independent qualification receipt; include source/workflow/run/platform/digest/test identities.'),
  T('any phase','test/tool/source/context/platform/output guard fails','precondition violated','refused','Stop; candidate directory may contain prior or partial outputs but no valid new qualification receipt is claimed.')
  ])

M('S69','Cross-platform qualification promotion into host payload overlay',
  'All native candidates and independent receipts; trusted source/workflow/run; exact required platform set; immutable in-memory payload snapshots; pinned create-only output.',
  'collecting;all qualified;release manifest built;per-host payload writing;promotion receipt written;partial unavailable',
  [PK+'|stage_artifact_host_payloads and pinned stage classes|111-626'],[
  T('collecting','stage promotion','new real output parent; one independent receipt per candidate; trusted protected context','collecting','Validate each native format/architecture/hash, exact supported version/protocol/schema and receipt source/run/test binding.'),
  T('collecting','all candidates verified','required platform set exact, no duplicates/missing/extra','all qualified','Hold immutable binary/receipt bytes; validate optional context finite evidence.'),
  T('all qualified','build release manifest','platform identities agree','release manifest built','Create five-key release manifest plus optional sixth context_qualification when any candidate supplies context evidence.'),
  T('release manifest built','write host overlays','validated canonical host descriptors','per-host payload writing','Create pinned create-only output; write identical qualified binary/manifest payload under each host-specific install path.'),
  T('per-host payload writing','all host writes succeed','byte identities fixed','promotion receipt written','Write artifact-promotion.json last, with exact host map, payload digests, qualification identities and context observation binding.'),
  T('any write','I/O/path identity failure','partial destination may exist','partial unavailable','Stop; output path remains create-only, so caller must inspect/discard failed staging and choose a fresh output.','Do not claim multi-file atomic overlay or enable a source checkout from this staging operation.')
  ])

M('S70','Native payload verification and create-only installation',
  'VerifiedPromotionPayload immutable bytes; pinned destination directory handle; binary write cursor; manifest availability; versioned-upgrade refusal.',
  'source unverified;source verified;destination created;binaries written;manifest installed;available;partial unavailable;existing refused',
  ['tools/install-artifact-payload.py|load_payload, load_promotion_receipt, _install_payload_bytes|1-292'],[
  T('source unverified','load payload','bounded regular files; exact schema incl optional context qualification; native-tested/magic/hash valid','source verified','Read immutable manifest/binary bytes; reject duplicates/unsafe platform/file entries.'),
  T('source unverified','load promoted payload','trusted receipt hash/source/workflow/run/host; exact source file set and qualification binding','source verified','Return immutable snapshot; installation never reopens unverified source paths.'),
  T('source verified','install','POSIX supported; safe descriptor plugin path; pinned no-follow ancestors; destination absent','destination created','Create helpers/artifacts exactly once with pinned directory handle.'),
  T('source verified','install','destination already exists','existing refused','Refuse overwrite; require reviewed versioned upgrade.','No automatic in-place update/uninstall lifecycle is implemented by this installer.'),
  T('source verified','install on Windows developer path','os.name==nt','refused','Developer installer fails closed; Windows payload installation is release-packaging path only.'),
  T('destination created','write binaries','exclusive safe relative names','binaries written','Write all bytes, fsync and set executable permissions.'),
  T('binaries written','write manifest last','binary writes complete','manifest installed then available','Exclusive-create release.json, fsync file then directory; manifest availability is final entrypoint signal.'),
  T('destination created or binaries written','write/fsync failure','multi-file operation interrupted','partial unavailable','Close handles and leave partial create-only directory.','No rollback or PATH fallback; do not retry same path blindly or claim plugin enabled.')
  ])

M('S71','Qualified release package cohort construction and verification',
  'Exact Git source commit/tree; immutable promotion snapshots; exact npm packer identity; archive members, archive bytes and per-host cohort receipt.',
  'source pinned;members derived;archives built;cohort written;verification pending;verified;refused/partial',
  [PK+'|_expected_release_package_members, build_artifact_release_packages, verify_artifact_release_packages|627-732;999-1578'],[
  T('source pinned','derive members','exact Git archive at full source commit + trusted promotion snapshot','members derived','Read Claude/Codex/Pi source members from commit; reject preexisting native payload; transform host catalogs; overlay identical promoted bytes; require canonical license/notices.'),
  T('members derived','select Pi npm members','exact reviewed npm executable/integrity; isolated environment','members derived','Use npm pack selection for Pi shipping whitelist; prohibit unknown/empty selected set; bind packer qualification production vs local-portability.'),
  T('members derived','build archives','admitted members','archives built','Deterministic tar/gzip Claude/Codex; exact npm pack for Pi; bind host versions, modes, sizes, paths, source/provenance/digests.'),
  T('archives built','write output','new pinned output directory','cohort written','Write three host archives and artifact-package-cohort.json last; create-only operation.'),
  T('cohort written','verify package cohort','exact supplied source/workflow/run/promotion digest','verification pending','Re-derive member expectations from Git/promotion; validate packer identity; inspect all archives and exact inventories.'),
  T('verification pending','all checks pass','archive/member bytes, modes, receipts and identities equal','verified','Return cohort evidence usable by downstream distribution steps.'),
  T('any construction/verification','mismatch/missing/extra/unsafe path/error','guard fails','refused/partial','Reject even if filenames or versions appear correct; output writes are not whole-cohort atomic.','Use fresh staging for recovery; never rewrite an immutable published version to hide drift.')
  ])

M('S72','Cold installed-host package execution and evidence',
  'Host/platform matrix cell; extracted exact archive; empty PATH and isolated home/repository; qualified binary; workflow and optional context results; receipt.',
  'package verified;extracted;native capabilities run;host workflow run;context cells run;receipt ready;refused',
  [PK+'|extract_artifact_release_package, cold_execute_artifact_host_payload|1579-1887'],[
  T('package verified','cold execute','native host/platform admitted; exact archive/cohort/promotion hashes','extracted','Extract safe exact members into isolated temp location; no runtime downloads; empty PATH fixture where required.'),
  T('extracted','invoke capabilities','manifest has qualified platform binary and exact hash','native capabilities run','Execute installed binary with bounded exact protocol request and verify response.'),
  T('native capabilities run','installed host workflow','exact installed bridge/hash and fixture authorization','host workflow run','Exercise artifact workflow through installed host bridge; validate proof fields including interruption reconciliation/finalization/absence of Markdown shadows.'),
  T('host workflow run','interpret Pi evidence','host==pi','host workflow run','Require synthetic-policy-event evidence and declared fixture prerequisite mode.','Do not report a real interactive Pi approval from synthetic cold test evidence.'),
  T('host workflow run','production context checks','require_production; platform context_qualification exists','context cells run','Run exact installed context cases for admitted hosts; Pi context scope remains unsupported.'),
  T('all applicable cells pass','emit receipt','proof identities exact and no stderr/error','receipt ready','Bind host/platform/source/workflow/run, package/binary/manifest/bridge and observed response hashes.'),
  T('any cell','missing qualification/nonzero/malformed/mismatch','guard fails','refused','No receipt success; dispose temporary isolated extraction.')
  ])

M('S73','Claude immutable distribution tag and marketplace channel promotion',
  'Qualified cohort digest; deterministic orphan distribution commit; immutable version tag observation; current channel head/tree/version; leased push/readback.',
  'staged;distribution derived;tag absent;tag same;tag conflict;channel planned;tag published;channel published;outcome unknown',
  ['tools/promote-claude-marketplace.py|promote|1-101','tools/promote-codex-marketplace.py|shared Git and deterministic commit helpers|45-91'],[
  T('staged','prepare promotion','new work path; full source commit; valid version; cohort/source/version exact','distribution derived','Stage exact qualified archive; deterministic orphan commit has fixed author/time/message bound to source/cohort/archive.'),
  T('distribution derived','observe immutable tag','remote absent','tag absent','Plan create of ca-dist-vVERSION.'),
  T('distribution derived','observe immutable tag','same deterministic commit','tag same','Idempotent distribution already exists; no rewrite.'),
  T('distribution derived','observe immutable tag','different commit','tag conflict','Refuse same-version different bytes.'),
  T('tag absent/same','observe marketplace','channel version parseable and newer than requested','refused rollback','Do not move channel backward.'),
  T('tag absent/same','plan channel','same current tree','channel planned unchanged','Reuse existing marketplace commit; avoids duplicate promotion commits.'),
  T('tag absent/same','plan channel','tree differs','channel planned','Create commit with prior channel and distribution as parents; malformed/unreadable current Claude version does not itself block rollback check because current_version=None skips comparison.'),
  T('channel planned','push requested','tag absent','tag published','Push immutable tag, then ls-remote readback must match exact deterministic commit.'),
  T('tag published or tag same','advance channel','planned channel differs','channel published','Push with force-with-lease at observed head, then exact readback.'),
  T('push/readback','transport or readback failure','remote mutation may already have happened','outcome unknown','Raise; retry in fresh work path re-observes tag/channel and derives same identities before further push.','No combined atomic tag+channel transaction; tag may exist while channel remains old.'),
  T('channel planned','push=false','local review mode','staged result','Return concrete refs/commits/hashes without remote mutation.')
  ])

M('S74','Codex immutable distribution, optional npm identity and channel promotion',
  'Qualified cohort/source/catalog bytes; deterministic orphan tag; catalog mode git/npm; expected head/npm integrity; append-only distribution ledger; leased channel push.',
  'qualified;immutable planned;immutable published;channel eligible;channel unchanged;channel planned;channel published;refused;outcome unknown',
  ['tools/promote-codex-marketplace.py|promote and ledger|1-210'],[
  T('qualified','prepare','new work path; exact source/version/catalog digest; git or npm mode','immutable planned','Stage exact package; derive deterministic ca-codex-dist-vVERSION orphan commit; optionally build exact npm bytes.'),
  T('immutable planned','observe tag','same version points elsewhere','refused','Reject immutable distribution identity conflict.'),
  T('immutable planned','push requested','tag absent','immutable published','Push tag then exact readback; same existing commit is no-op.'),
  T('immutable planned/published','advance_channel requested','immutable tag already observed at exact expected commit','channel eligible','Require tag preexist before channel advance; optional expected-marketplace-head is compare guard.'),
  T('channel eligible','npm channel','verified expected npm integrity+sha equal generated package','channel eligible','Require registry artifact identity to be supplied before changing channel to npm source.'),
  T('channel eligible','observe prior channel','parseable approved source shape and no version rollback','channel planned','Read old catalog/ledger, reject malformed/missing version or downgrade; preserve prior ledger entries and reject same-version record drift.'),
  T('channel eligible','same catalog and ledger','byte equality','channel unchanged','Reuse prior channel commit idempotently.'),
  T('channel planned','push requested','expected head still leased','channel published','Push channel commit with force-with-lease, then exact readback; includes old channel and distribution parents.'),
  T('any remote step','failure/readback drift','mutation may have occurred','outcome unknown','Stop; rerun with fresh work directory and remote re-observation.','Immutable tag creation and channel advance are separate operations by design; do not infer rollback from failed final response.'),
  T('any planning','push=false','review path','concrete result','Return exact candidate refs/commits/package hashes without writing remote.')
  ])

M('S75','Generated host surface projection and drift gate',
  'Canonical templates/host descriptors/command registry; expected rendered byte map; on-disk host files; check/write mode.',
  'source validation;rendered;in sync;drifted;writing;orphans removed;partial output;invalid source',
  ['tools/build-surface.py|registry validation, render_all, check_all, write_all|121-1306'],[
  T('source validation','render host','descriptors/registry/templates/role catalogs valid','rendered','Resolve explicit host conditionals, relative resources, command/skill frontmatter and host-specific contracts; generate expected bytes.'),
  T('source validation','compatibility metadata','exact clockStarts/removalRequires/targets shape and fixed values','validated metadata','Require removalRequires literal minor-release-with-changelog-notice.','This validates vocabulary; it does not observe release history or authorize an actual compatibility removal.'),
  T('rendered','--check','all expected files byte-equal and no orphans','in sync exit 0','Read-only drift result.'),
  T('rendered','--check','missing/different/orphan files','drifted exit 1','List every detected path; canonical templates remain owner.'),
  T('rendered','write mode','current host expected map valid','writing','Write changed expected files directly; preserve equal files; then delete owned orphan generated files.'),
  T('writing','all hosts finish','writes/deletes succeed','orphans removed exit 0','Return changed count.'),
  T('any validation/write','source/descriptor invalid','guard fails','invalid source exit 2','Stop; earlier host writes can already exist because generation is per-host sequential.'),
  T('writing','I/O failure','direct writes may be partial','partial output','No cross-file transaction/rollback; rerun after repairing source/filesystem.')
  ])

M('S76','Canonical Python and package-notice synchronization',
  'Canonical Python basename set excluding _host.py; descriptor hooks targets; canonical notices; binary equality; per-file temp replacement.',
  'inventory;equal;drifted;copy staged;copy replaced;partial synchronization;failed',
  ['tools/sync-core.py|core_files, sync_notices, main|1-178'],[
  T('inventory','collect source/targets','nonempty canonical Python set and valid descriptors','inventory ready','Select shared .py files only; deliberately exclude per-host _host.py; include canonical LICENSE and THIRD_PARTY_NOTICES.'),
  T('inventory ready','--check','every selected copy byte-equal','equal exit 0','Report exact byte parity including line endings; no normalization.'),
  T('inventory ready','--check','missing/different copies or notices','drifted exit 1','List drift, no writes.'),
  T('inventory ready','write','source differs','copy staged','Write bytes to per-file .tmp-sync; notices and Python source copied independently.'),
  T('copy staged','os.replace','write succeeded','copy replaced','Atomically replace that one file; equal files untouched.'),
  T('copy sequence','later error','prior files already replaced','partial synchronization','Stop with exit 1; next run compares and completes only remaining drift.','No all-host atomic transaction; no orphan deletion for removed canonical Python names is implemented.'),
  T('inventory','invalid args/descriptors/no sources','guard fails','failed exit 2','Do not guess target hosts or synchronize per-host adapters.')
  ])

M('S77','Pi package metadata projection and release-advance guard',
  'Nested Pi manifest version/license; generated root npm metadata; base ref; shipped-payload diff; changelog heading; existing release tag.',
  'metadata expected;metadata drift;no shipped change;first introduction;advance required;advance valid;refused',
  [PK+'|render_package, expected_package, validate_pi_release_advance, pi_release_guard, main|1888-2259','plugins/ca-pi/tools/build.mjs|bundled build outputs|1-140'],[
  T('nested metadata','render root package','Pi host descriptor + nonempty version/license','metadata expected','Generate deterministic root scoped npm package metadata/files whitelist/engines/Pi extension and skill entrypoints.'),
  T('metadata expected','check/write','root bytes differ','metadata drift or replaced','Check reports mismatch; write regenerates root bytes from canonical nested values.'),
  T('base comparison','release guard','no shipped Pi payload/root change; tools source-only excluded','no shipped change','Return pass without version demand; shipped extensions outside tools remain in scope.'),
  T('base comparison','base invalid','ref cannot resolve','refused','Stop rather than treat missing base as first release.'),
  T('payload changed','base lacks Pi manifest','new Pi introduction','first introduction','Require root version equality and exact current changelog heading; supported initial introduction path.'),
  T('payload changed','base has Pi package','normal release','advance required','Require valid strict higher SemVer, regenerated root version change, changelog change and newly introduced exact version heading.'),
  T('advance required','all metadata guards pass','ca-pi-vVERSION tag absent','advance valid','Return release metadata consistency pass.'),
  T('advance required','missing advance/headings/root change or existing tag','any guard fails','refused','Return exit 1; no automatic bump/tag/publish.'),
  T('TypeScript build','bundle selected entrypoints','build deps available','generated bundle outputs','Build parent extension, child helper, private approval and supervisor bundles from explicit sources.','This audit reads TypeScript source; no equality rebuild against committed JS was run.')
  ])

F('SF01','Pi author child has no usable mutation authorization path',
  [PI+'child-extension.ts:ensureBuiltins:65-77',PI+'tool-guard.ts:confirmationUi:444-454',PI+'policy.ts:execute permission policy',PI+'runner.ts:RPC inert child launch'],
  'The role advertises write/edit/bash but the default execute policy asks for every mutator and the child has RPC UI. The child also lacks the approved-permission audit callback. Successful handshake/read capability therefore does not imply author capability.',
  'Keep final guard fail-closed; define a parent-issued task-scoped delegated capability with explicit paths/commands, expiry/session/generation, and parent-owned durable audit. Until that contract exists, advertise this child role as read-only/unavailable for authorship.',
  confidence='source-confirmed and isolated source-module probe',probes=['probe-pi-child-mutation.mjs','probe-pi-child-mutation-result.json'])
F('SF02','Pi ready state can outlive failed persona initialization',
  [PI+'extension.ts:session_start markReady before loadPersona and combined catch'],
  'A persona read failure is stored as bridge degradation after readiness. A later successful bridge refresh can clear that degraded state while persona remains empty, with no persona retry edge.',
  'Make persona loading an explicit prerequisite or a durable independent unavailable capability. Ready/governed rendering must depend on the same actual prerequisite vector as prompt construction.')
F('SF03','Sidebar installs after disposal when metrics promise resolves late',
  [PI+'sidebar-manager.ts:autoInstall/dispose',PI+'footer.ts:generation-protected installation'],
  'A disposed session can reclaim terminal width and renderer hooks. The source-module probe disposed while metrics was pending, then observed installed=true and columns 140→99 after resolving metrics.',
  'Apply the existing footer generation/lease pattern to sidebar installs, checking before and after await and before patching. Disposal invalidates every pending install.',
  confidence='source-confirmed and isolated source-module probe',probes=['probe-pi-sidebar-dispose.mjs','probe-pi-sidebar-dispose-result.json'])
F('SF04','Qualified production artifact manifests are rejected by farm parser',
  [FARM+'farm.ts:installedArtifactBinary:270-276',PK+':stage_artifact_host_payloads:569-579',PK+':cold_execute_artifact_host_payload:1790-1792','tools/install-artifact-payload.py:load_payload:75-84'],
  'Farm accepts exact top-level keys format/version/protocol/schema_version/binaries. Promotion adds context_qualification, and production cold execution requires the current platform in that field. Thus a production-qualified manifest shape fails farm admission before native binary execution. This is current-source incompatibility, not an assertion that a particular published release was observed failing.',
  'Use one versioned release-manifest decoder/contract across farm, installers and verification; explicitly admit and validate the supported optional context field. Add an exact qualified-package farm admission test before loosening any trust checks.')
F('SF05','Farm receipt failure is not a safe author-redispatch instruction',
  [FARM+'farm.ts:run report finalization:3282-3697',FARM+'farm.ts:prepareWorktree:1858-1880'],
  'Exit 3 can follow successful task commits/merges and integration worktree cleanup. A new invocation force-resets integration to base and replaces same task branches/worktrees. Reused FARM_RUN_ID also opens an existing run directory and truncates stream evidence.',
  'Split recover-receipt from retry-author. Persist an exclusive run identity and durable task/integration commit references, inspect existing refs on recovery, and reproduce missing receipts without scheduling authors. Reject run-ID reuse unless an explicit recovery contract verifies it.')
F('SF06','Farm gate retry loses containment failure',
  [FARM+'exec.ts:timeout results',FARM+'farm.ts:runGate:688-703',FARM+'farm.ts:runTask gate failure retry',FARM+'mutation.ts:cleanupFailed handling'],
  'The executor distinguishes timeout with verified cleanup (124) from unverified cleanup (125/cleanupFailed). runGate reduces all nonzero outcomes to ordinary gate failure, allowing outer author reset/retry; mutation path treats unverified containment as fatal.',
  'Return operation result, cancellation reason and containment status as separate typed fields through every caller. Block mutation/reset/retry until prior containment is verified, reusing the mutation path policy where applicable.')
F('SF07','Farm Git observation failure can appear as no drift',
  [FARM+'farm.ts:checkDrift'],
  'Failed diff/ls-files observations are replaced with empty arrays. Both failures can yield a clean-looking drift result.',
  'Use observed-clean/observed-dirty/unavailable states; retry bounded read-only Git probes if appropriate, and stop effects when absence cannot be established.')
F('SF08','Sandbox dependency cache identity is tied to random checkout basename',
  [SB+'create.ts:defaultBuildImage',SB+'build.ts:imageTag',SB+'dephash.ts:computeDepHash'],
  'Two creates with identical dependency files compute the same hash but random temporary checkout names produce different Docker tags, defeating intended cross-create cache reuse. Current caller also omits the available Nixpacks version component.',
  'Build a stable cache key from dependency inputs, supported platform and actual builder/toolchain version. Keep repository name only as a cosmetic label; verify existing image provenance before reuse.',
  confidence='source-confirmed and isolated source-module probe',probes=['probe-sandbox-lifecycle.mjs','probe-sandbox-lifecycle-result.json'])
F('SF09','Sandbox output overflow kills observation client without stopping workload',
  [SB+'docker.ts:overflow handling',SB+'exec.ts:timeout/abort cleanup branch'],
  'Overflow is returned as ordinary exit 1 rather than a distinct interrupted reason. exec stops container only for timeout/abort; probe observed no stop after overflow.',
  'Carry overflow as explicit interrupted outcome and run the same verified containment policy as other lost-observation paths. Report stop outcome independently from command failure.',
  confidence='source-confirmed and isolated source-module probe',probes=['probe-sandbox-lifecycle.mjs','probe-sandbox-lifecycle-result.json'])
F('SF10','Sandbox cleanup and discovery sometimes claim more than observed',
  [SB+'claude-inside.ts:firewall failure cleanup',SB+'create.ts:compensation',SB+'registry.ts:list helpers',SB+'destroy.ts:verified destroy comparison'],
  'Claude-inside error says destroyed after an ignored rm result that may be pre-aborted; create compensation ignores remove results; registry view returns [] when Docker listing fails. destroy/prune already contains a better explicit unknown/re-observe pattern.',
  'Reuse destroy/prune observation contracts for create/Claude compensation and registry UI. Keep resource IDs and cleanup unknown until an un-aborted read confirms absence. Propagate cancellation through clone/build and bound helper cleanup.')
F('SF11','Site search handles loader failure but not query/result-data failure',
  [SC+'Search.astro:perform search and show-all handlers'],
  'Pagefind module import has retry state; search/data promises do not. Rejection can preserve stale current-looking results or disable show-all indefinitely.',
  'Give query and expansion their own error/retry state and finally cleanup, bound to the existing query generation token; retain input and clearly mark old results stale.')
F('SF12','Private Pi artifact prompt is not general installed Pi approval support',
  [PI+'approval-entry.ts:39',PI+'approval-dialog.ts:private one-shot guards',PI+'compatibility.ts:supported 1.1.0 runtime',PK+':cold execution synthetic Pi approval evidence'],
  'Private entry requires exact Pi 1.0.2 while supported runtime compatibility is 1.1.0. It rejects ordinary agent flows; cold-package workflow reports synthetic-policy-event evidence for Pi. This cannot support a broad claim that all installed Pi artifact approvals are host-observed.',
  'Publish a host/capability/evidence-mode matrix from actual admission contracts. Version private approval separately and qualify it on supported Pi before describing it as usable authority; preserve ordinary progress independent of optional attestation.')
F('SF13','Surface and release build helpers have recoverable partial-write states',
  ['tools/build-surface.py:write_all','tools/sync-core.py:main','site/scripts/generator/generate.ts:generated tree replacement','site/scripts/generate-academy.ts:output root removal','site/scripts/pagefind-build.ts:remove then rename'],
  'Canonical generation is deterministic but many multi-file writes are not atomic; some remove old output before late render/rename failures. This is acceptable only if callers treat failed builds as unusable and rerun from canonical input.',
  'Build into a complete fresh staging tree, validate there, then swap an owned output root where practical. Do not expand ordinary file tools into a distributed saga; apply durable receipts primarily to irreversible/external effects.')
F('SF14','Compatibility metadata validates a removal slogan, not release-history authorization',
  ['tools/build-surface.py:_validate_compatibility_policy:423-439'],
  'The literal removalRequires value is shape-checked during surface generation. It does not enforce elapsed releases, version floors, release publication status or actual command removal.',
  'Keep provenance-aware removal gate separate and authoritative; generate compatibility prose from that enforceable contract instead of implying this registry literal proves removal eligibility.')
F('SF15','Claude and Codex promotion intentionally differ but share unknown-outcome recovery',
  ['tools/promote-claude-marketplace.py:promote','tools/promote-codex-marketplace.py:promote'],
  'Both pin immutable distribution commits, refuse same-version drift, lease channel writes and read back. Codex requires prior immutable tag before channel advance and rejects malformed current version; Claude combines tag/channel flow and skips downgrade comparison if prior version cannot be read.',
  'Preserve host distribution differences. Share verified-ref outcome types and explicitly reject unknown current-channel version if monotonicity is required; provide fresh-work re-observation after any uncertain push rather than blind retry.')
F('SF16','Site drawer reconnect cleanup may duplicate local handlers',
  [SC+'SplashDocsRail.astro:setup/cleanup'],
  'Cleanup removes document Escape handler and resets initialized marker but does not remove local opener/close/tray handlers; reconnecting the same element can bind duplicate toggles.',
  'Own all listeners with one AbortController per connection, or retain the once-bound marker while reattaching document listeners. Add one connect-disconnect-reconnect behavior check only if this lifecycle is supported.',confidence='source-confirmed; browser reconnect behavior not executed')

def emit():
    ledger=(OUT/'surfaces-read-files.txt').read_text().splitlines()
    full=[line.split('\t')[1] for line in ledger if line.startswith('FULL\t')]
    inventory=[line.split('\t')[1] for line in ledger if line.startswith('INVENTORY_ONLY\t')]
    targeted=[line.split('\t')[1:] for line in ledger if line.startswith('TARGETED\t')]
    code_markup=[line.split('\t')[1] for line in ledger if line.startswith('CODE_AND_MARKUP\t')]
    for machine in machines:
        for source in machine['sources']:
            p=REPO/source['path']
            if p.exists() and source['lines'].startswith('1-'):
                source['lines']=f'1-{len(p.read_text().splitlines())}'
        # Use full actual-source refs rather than pretend approximate per-symbol positions.
        for row in machine['transitions']:
            if not row.get('source'):
                row['source']='; '.join(f'{s["path"]}:{s["symbol"]}:{s["lines"]}' for s in machine['sources'])
    result=dict(repository='arbiterForge/codeArbiter',commit=COMMIT,
      claim_scope='Current pinned development source, not a released-artifact qualification. No source edits, remote writes, package installation, real Docker run or real Pi session were performed.',
      definition='A machine has persisted or retained state that changes which subsequent events/effects are admitted. Independent dimensions remain distinct; pure enum catalogs, parsers and rendering loops are not automatically counted as product lifecycles.',
      machines=machines,findings=findings,
      coverage=dict(fully_read=full,complete_code_and_markup_with_literal_css_omitted=code_markup,targeted_read=targeted,inventory_only_not_semantically_audited=inventory,
        classified_without_new_machine=[
          dict(paths=['plugins/ca/tools/redactor.ts'],classification='Fully read stateless per-call secret-shaped-line/PEM-span filter and filename denylist; scanner loop is not a retained product lifecycle.'),
          dict(paths=['plugins/ca-sandbox/tools/smoke.ts'],classification='Fully read toolchain smoke function returning true; no product state.'),
          dict(paths=['site/scripts/execution-maps/model.ts','site/scripts/execution-maps/workflows.ts'],classification='Fully read explicit editorial teaching graphs: feature plus sprint/dependency/ADR/release/greenfield/brownfield. reviewedAt pins historical citation commits, optional currentPath/currentQuote records current owners/wording. validateExecutionMap checks node/source/edge shape, ordering and reachability; getWorkflow selects declared data or throws. Neither executes, authorizes, persists or proves depicted workflows.'),
          dict(paths=['site/src/components/Head.astro','site/src/components/Sidebar.astro','site/src/components/SidebarSublist.astro'],classification='Complete code/markup inspected. Head instantiates imported Astro ClientRouter. Sidebar instantiates imported Starlight SidebarPersister/RestorePoint; initial group open is current descendant link OR !collapsed. Third-party router/persistence internal event/storage semantics are not part of reviewed repo source and not inferred from names.'),
          dict(paths=['site/src/components/AcademyLesson.astro','site/src/components/AcademyTrack.astro','site/src/components/AcademyWayfinding.astro','site/src/components/ArbiterIcon.astro','site/src/components/ArtifactWorkbench.astro','site/src/components/CaTocList.astro','site/src/components/CapturedRun.astro','site/src/components/CheckpointMap.astro','site/src/components/ConceptNavigator.astro','site/src/components/DecisionRoutes.astro','site/src/components/DeliveryStory.astro','site/src/components/Header.astro','site/src/components/HookProof.astro','site/src/components/HostViews.astro','site/src/components/LimitsAndEvidence.astro','site/src/components/PageContext.astro','site/src/components/PageTitle.astro','site/src/components/ProjectBlueprint.astro','site/src/components/ReaderJourney.astro','site/src/components/RecoveryExplorer.astro','site/src/components/ReleaseApplicability.astro','site/src/components/SmartsComparison.astro','site/src/components/StatuslineGallery.astro','site/src/components/ThemeSelect.astro','site/src/components/TrustRow.astro','site/src/components/WorkflowDirectory.astro','site/src/components/WorkflowMap.astro'],classification='Complete frontmatter/markup inspected: build-time validated rendering, explanatory data, links/native details/video, empty theme selector, or compositions of the already inventoried ExampleChoices/ExecutionMap/AcademyBookmark controls; no additional custom JS state owner. Native browser disclosure/media state is delegated rather than implemented here.')],
        delegated=['.github workflows/actions/scripts and native Go: native_states','Core Python and unique host Python other than _workgithub/_taskboardlib/_releaselib: hook_states','Prose workflows/ADRs/model-guided release and site residual scripts: root'],
        exclusions=['Generated JavaScript bundles were inventoried but not rebuilt/equality-verified against TypeScript; exact distributed artifact qualification remains open.','No actual upstream Pi host/interactive TUI/process-tree platform matrix or Docker daemon was exercised. Isolated probes use source imports with fake dependencies.','Inventory-only entries are explicit gaps in this agent report, not assertions that those files have no behavior.','No excluded employer/downstream context was used.']),
      recommendation=dict(decision='Adopt one explicit transition-and-effect contract at authority and external-effect boundaries, with independent state axes and observational adapters; migrate incrementally under existing behavior.',
        contract=['state schema/version and stable aggregate identity','event identity and expected revision/generation','guard result with observed evidence, distinct unavailable/unknown states','pure transition decision returning allowed effects','durable claim-before-effect where non-idempotent/external effects require recovery','effect outcome separate from work outcome, containment, evidence persistence and UI projection','safe reconciliation/retry action that never repeats non-idempotent effects blindly','derived human/agent status, allowed next actions, docs and fixture traces'],
        migration=['Freeze exact-source traces and existing host differences before changing semantics.','Introduce typed result/transition wrappers around existing implementations, initially observing/shadow-comparing.','Repair concrete mismatches (Pi capability contract, manifest parser, disposal, lost containment/observation) through small targeted fixes.','Move irreversible/external delivery to durable claim/observe/reconcile contracts, borrowing existing work-GitHub/native patterns.','Derive capability/status/docs from actual contracts; keep UI-only state lightweight.','Qualify exact generated/distributed artifacts per host/platform before enabling changed behavior; preserve rollback to previous package/state reader.'],
        limitations='No design can honestly guarantee better UX/DX/AX always and zero breakage. Preserve compatibility through additive readers/events, bounded migrations, exact-artifact evidence and rollback. Avoid a universal giant FSM or mandatory framework rewrite.'))
    (OUT/'surfaces.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# Host, farm, sandbox, site and release-helper state-machine audit','',
      f'Authority: `arbiterForge/codeArbiter@{COMMIT}`. This is pinned development-source behavior; it is not a released-package or live-host qualification.','',
      f'{len(machines)} machine families, {sum(len(m["transitions"]) for m in machines)} transition rows, {len(findings)} findings. Full read and explicit gap manifest: `surfaces-read-files.txt`.','',
      '## Recommended decision','',result['recommendation']['decision'],'',result['recommendation']['limitations'],'',
      'Model independent axes explicitly: lifecycle, authority/trust, task outcome, process containment, external-effect delivery, evidence publication, and UI availability. A green task is not proof of cleanup; failed acknowledgment is not proof an effect did not happen; missing observation is not clean state. Existing native work claims/reconciliation and footer generations supply concrete local patterns.','',
      '## Findings','']
    for f in findings:
        lines += [f'### {f["id"]}: {f["title"]}','',f'**Evidence level:** {f["confidence"]}.','',f['implication'],'',f'**Correction:** {f["recommendation"]}','',
                  '**Source:** '+ '; '.join(f'`arbiterForge/codeArbiter@{COMMIT}:{p}`' for p in f['evidence'])+'.','']
        if f['probes']: lines += ['**Probe artifacts:** '+', '.join('`'+p+'`' for p in f['probes'])+'.','']
    lines += ['## Complete transition tables','',
      'Each row includes the guard and next state because state × event × side effects alone would hide rejected and uncertain outcomes. A slash or “or” denotes explicitly grouped equivalent branches, not an assertion that all dimensions form one scalar state.','']
    def cell(v): return str(v).replace('|','\\|').replace('\n','<br>')
    for m in machines:
        lines += [f'### {m["id"]}: {m["name"]}','',f'**State owner/storage:** {m["state_storage"]}','',
          '**Sources:** '+ '; '.join(f'`arbiterForge/codeArbiter@{COMMIT}:{s["path"]}` ({s["symbol"]}, lines {s["lines"]})' for s in m['sources'])+'.','']
        if m['notes']: lines += [m['notes'],'']
        lines += ['| State | Event | Guard | Next state | Side effects | Failure / retry |','|---|---|---|---|---|---|']
        for row in m['transitions']:
            lines.append('| '+' | '.join(cell(row[k]) for k in ['from','event','guard','to','effects','failure_retry'])+' |')
        lines.append('')
    lines += ['## Coverage and limits','',f'{len(full)} complete files read by this agent; {len(code_markup)} additional Astro components have complete code/markup reads with literal CSS omitted; {len(inventory)} explicitly inventoried-only files are handed to root or remain stated gaps. See JSON coverage and read manifest for exact paths.','',
      'The three source-import probes are bounded local fixtures. They establish specific reachable branches, not platform certification or absence of other defects. Generated bundles, actual host trust dialogs, real container teardown and published archives still require exact-artifact validation.','',
      '## Canon / claim-registry delta','',
      'Separate “role listed”, “handshake succeeded”, “can read”, “can mutate under delegated scope”, “host-observed approval”, “synthetic fixture approval”, “native-qualified candidate”, “production-qualified package”, “task integrated”, “containment verified”, and “receipt published”. Preserve Claude, Codex and Pi differences. Emit allowed next actions and evidence scope from actual implementations.','',
      '## Decisions requiring approval','',
      'This audit makes no repository or external application changes. Implementation approval is required before introducing delegated Pi author authority, changing compatibility-removal policy, or migrating durable state formats. Routine bug-fix proposals should be made concrete against current exact-source behavior first.','',
      '## Verification still required','',
      'Exact source-to-bundle equality, qualified package admission into farm, supported Pi interactive and RPC host matrix, Windows process-tree containment, Docker cancellation/overflow/cleanup against a real daemon, browser disconnect/reconnect behavior, and backward-readable state migrations.','',
      '## Recommended next action','',
      'Start with an additive transition/result contract and tests at the already demonstrated contradiction points. Keep existing behavior as a compatibility oracle, fix specific violated invariants, then generate capability/status/help from the same authoritative contracts.']
    (OUT/'surfaces.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'machines':len(machines),'transitions':sum(len(m['transitions']) for m in machines),'findings':len(findings),'fully_read':len(full),'paths':[str(OUT/'surfaces.json'),str(OUT/'surfaces.md'),str(OUT/'surfaces-read-files.txt')]}))

if __name__=='__main__': emit()



