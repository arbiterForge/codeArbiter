// Package observation defines the closed, content-addressed boundary between
// host-owned evidence producers and authority-bearing workflow events.
package observation

import (
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const root = ".codearbiter/.artifacts"

var digest = regexp.MustCompile(`^[0-9a-f]{64}$`)

func text() map[string]any { return map[string]any{"type": "string", "minLength": int64(1)} }
func hash() map[string]any { return map[string]any{"type": "string", "pattern": digest.String()} }
func closed(properties map[string]any, required ...string) map[string]any {
	return map[string]any{"type": "object", "properties": properties, "required": model.List(required...), "additionalProperties": false}
}
func subjectSchema() map[string]any {
	return closed(map[string]any{"artifact_id": text(), "normative_sha256": hash(), "record_id": text()}, "artifact_id", "normative_sha256", "record_id")
}
func manifestSchema() map[string]any {
	return closed(map[string]any{
		"format": map[string]any{"const": "codearbiter.verification-inputs/0.1.0"},
		"engine": text(), "platform": text(), "engine_toolchain": text(),
		"roots":               map[string]any{"type": "array", "items": text()},
		"exclude_directories": map[string]any{"type": "array", "items": text()},
		"entries":             map[string]any{"type": "object"},
	}, "format", "engine", "platform", "engine_toolchain", "roots", "exclude_directories", "entries")
}

// ContextSchema describes the exact engine-calculated material a producer is
// allowed to observe. Task and scope definitions remain the canonical model
// values; their independently supplied hashes are checked during capture.
func ContextSchema() map[string]any {
	common := map[string]any{
		"format":  map[string]any{"const": "codearbiter.evidence-context/0.1.0"},
		"subject": subjectSchema(), "input_sha256": hash(), "input_manifest": manifestSchema(),
		"spec_sha256": hash(), "plan_sha256": hash(),
	}
	taskProps := map[string]any{}
	for k, v := range common {
		taskProps[k] = v
	}
	taskProps["activity"] = map[string]any{"enum": model.List("verification", "spec_review")}
	taskProps["task_sha256"] = hash()
	taskProps["task"] = map[string]any{"type": "object"}
	taskProps["commands"] = map[string]any{"type": "array", "items": closed(map[string]any{"definition_sha256": hash(), "definition": map[string]any{"type": "object"}}, "definition_sha256", "definition")}
	task := closed(taskProps, "format", "activity", "subject", "input_sha256", "input_manifest", "spec_sha256", "plan_sha256", "task_sha256", "task", "commands")
	scopeProps := map[string]any{}
	for k, v := range common {
		scopeProps[k] = v
	}
	scopeProps["activity"] = map[string]any{"const": "quality_review"}
	scopeProps["base_input_sha256"] = hash()
	scopeProps["task_hashes"] = map[string]any{"type": "object", "additionalProperties": hash()}
	scopeProps["scope_baseline"] = map[string]any{"type": "object"}
	scopeProps["tasks"] = map[string]any{"type": "array", "items": map[string]any{"type": "object"}}
	scope := closed(scopeProps, "format", "activity", "subject", "input_sha256", "input_manifest", "spec_sha256", "plan_sha256", "base_input_sha256", "task_hashes", "scope_baseline", "tasks")
	prompt := closed(map[string]any{
		"format":   map[string]any{"const": "codearbiter.evidence-context/0.1.0"},
		"activity": map[string]any{"enum": model.List("approval", "prerequisite", "reconciliation", "farm_authorization")},
		"subject":  subjectSchema(), "input_sha256": hash(), "prompt_sha256": hash(),
		"record_sha256": hash(), "record": map[string]any{"type": "object"},
	}, "format", "activity", "subject", "input_sha256", "prompt_sha256", "record_sha256", "record")
	return map[string]any{"oneOf": []any{task, scope, prompt}}
}

func testResultSchema() map[string]any {
	return closed(map[string]any{"name": text(), "status": map[string]any{"const": "pass"}}, "name", "status")
}
func commandResultSchema() map[string]any {
	return closed(map[string]any{
		"definition_sha256": hash(), "exit": map[string]any{"type": "integer", "minimum": int64(0), "maximum": int64(255)},
		"tests": map[string]any{"type": "array", "items": testResultSchema()}, "stdout_sha256": hash(), "stderr_sha256": hash(),
	}, "definition_sha256", "exit", "tests", "stdout_sha256", "stderr_sha256")
}
func commandBindingSchema(qualified bool) map[string]any {
	contract := closed(map[string]any{
		"definition_sha256": hash(), "argv": map[string]any{"type": "array", "items": text(), "minItems": int64(1)},
		"cwd": text(), "cwd_filesystem_id": text(), "workspace_root": text(), "workspace_filesystem_id": text(),
		"git_common_dir": text(), "git_common_filesystem_id": text(), "executable_sha256": hash(),
	}, "definition_sha256", "argv", "cwd", "cwd_filesystem_id", "workspace_root", "workspace_filesystem_id", "git_common_dir", "git_common_filesystem_id", "executable_sha256")
	if qualified {
		properties := model.M(contract["properties"])
		properties["collector_profile"] = map[string]any{"enum": model.List("python-unittest-text/0.1.0", "codearbiter-named-lines/0.1.0", "vitest-verbose/0.1.0", "playwright-json/0.1.0", "exit-only/0.1.0")}
		properties["launch_files"] = map[string]any{"type": "array", "minItems": int64(1), "maxItems": int64(4), "items": launchFileSchema()}
		contract["required"] = append(model.A(contract["required"]), "collector_profile", "launch_files")
	}
	return contract
}
func workspaceSchema() map[string]any {
	return closed(map[string]any{
		"root": text(), "filesystem_id": text(), "git_common_dir": text(), "git_common_filesystem_id": text(),
		"head": text(), "status_sha256": hash(), "content_sha256": hash(),
	}, "root", "filesystem_id", "git_common_dir", "git_common_filesystem_id", "head", "status_sha256", "content_sha256")
}
func verificationResultSchema(qualified bool) map[string]any {
	return closed(map[string]any{
		"environment_sha256": hash(),
		"command_bindings":   map[string]any{"type": "array", "items": commandBindingSchema(qualified), "minItems": int64(1)},
		"workspace_before":   map[string]any{"type": "array", "items": workspaceSchema(), "minItems": int64(1)},
		"workspace_after":    map[string]any{"type": "array", "items": workspaceSchema(), "minItems": int64(1)},
		"commands":           map[string]any{"type": "array", "items": commandResultSchema(), "minItems": int64(1)},
	}, "environment_sha256", "command_bindings", "workspace_before", "workspace_after", "commands")
}

// Review producer profiles. Each profile carries only its own host's launch
// correlation shape, so one host's launch evidence can never be relabelled as
// another's.
const (
	CodexReviewProfile         = "codex-review/0.1.0"
	CodexNativeV1ReviewProfile = "codex-native-v1/0.145.0"
	ClaudeReviewProfile        = "claude-review/0.1.0"
	// ClaudeReviewer is the plugin-shipped read-only reviewer agent a Claude
	// review launch must pin.
	ClaudeReviewer = "ca:authority-reviewer"
)

func reviewDecisionSchema() map[string]any {
	finding := closed(map[string]any{"severity": map[string]any{"enum": model.List("BLOCK", "WARN", "INFO")}, "code": text(), "message": text()}, "severity", "code", "message")
	return closed(map[string]any{
		"format": map[string]any{"const": "codearbiter.review-decision/0.1.0"}, "request_id": hash(), "target_sha256": hash(), "contract_sha256": hash(),
		"decision": map[string]any{"const": "pass"}, "coverage": map[string]any{"type": "array", "items": text(), "minItems": int64(1)},
		"findings": map[string]any{"type": "array", "items": finding}, "assessment": text(),
	}, "format", "request_id", "target_sha256", "contract_sha256", "decision", "coverage", "findings", "assessment")
}
func claudeReviewResultSchema() map[string]any {
	reviewer := map[string]any{"const": ClaudeReviewer}
	launch := closed(map[string]any{
		"parent_session_id": text(), "parent_prompt_id": text(), "tool_use_id": text(), "post_confirmed": map[string]any{"const": true},
		"agent_id": text(), "agent_type": reviewer, "subagent_type": reviewer, "model": text(), "resolved_model": text(),
		"first_stop": map[string]any{"const": true},
	}, "parent_session_id", "parent_prompt_id", "tool_use_id", "post_confirmed", "agent_id", "agent_type", "subagent_type", "model", "resolved_model", "first_stop")
	return closed(map[string]any{"launch": launch, "decision": reviewDecisionSchema()}, "launch", "decision")
}
func codexNativeV1ReviewResultSchema() map[string]any {
	uuid := map[string]any{"type": "string", "pattern": `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`}
	launch := closed(map[string]any{
		"parent_session_id": text(), "parent_turn_id": text(), "tool_use_id": text(), "post_confirmed": map[string]any{"const": true},
		"agent_id": uuid, "agent_type": map[string]any{"const": "default"}, "codex_review_profile": map[string]any{"const": CodexNativeV1ReviewProfile},
		"child_turn_id": uuid, "fork_context": map[string]any{"const": false}, "first_stop": map[string]any{"const": true},
	}, "parent_session_id", "parent_turn_id", "tool_use_id", "post_confirmed", "agent_id", "agent_type", "codex_review_profile", "child_turn_id", "fork_context", "first_stop")
	return closed(map[string]any{"launch": launch, "decision": reviewDecisionSchema()}, "launch", "decision")
}
func reviewResultSchema() map[string]any {
	launch := closed(map[string]any{
		"parent_session_id": text(), "parent_turn_id": text(), "tool_use_id": text(), "post_confirmed": map[string]any{"const": true},
		"agent_id": text(), "agent_type": text(), "task_name": text(), "fork_turns": map[string]any{"const": "none"},
	}, "parent_session_id", "parent_turn_id", "tool_use_id", "post_confirmed", "agent_id", "agent_type", "task_name", "fork_turns")
	finding := closed(map[string]any{"severity": map[string]any{"enum": model.List("BLOCK", "WARN", "INFO")}, "code": text(), "message": text()}, "severity", "code", "message")
	decision := closed(map[string]any{
		"format": map[string]any{"const": "codearbiter.review-decision/0.1.0"}, "request_id": hash(), "target_sha256": hash(), "contract_sha256": hash(),
		"decision": map[string]any{"const": "pass"}, "coverage": map[string]any{"type": "array", "items": text(), "minItems": int64(1)},
		"findings": map[string]any{"type": "array", "items": finding}, "assessment": text(),
	}, "format", "request_id", "target_sha256", "contract_sha256", "decision", "coverage", "findings", "assessment")
	return closed(map[string]any{"launch": launch, "decision": decision}, "launch", "decision")
}
func promptResultSchema() map[string]any {
	return closed(map[string]any{
		"host": text(), "session_id": text(), "prompt_sha256": hash(),
	}, "host", "session_id", "prompt_sha256")
}
func observationSchema(format string, current bool) map[string]any {
	base := map[string]any{
		"format": map[string]any{"const": format}, "kind": map[string]any{"enum": model.List("approval", "prerequisite", "verification", "spec_review", "quality_review", "reconciliation", "farm_authorization")},
		"subject": subjectSchema(), "context_ref": text(), "context_sha256": hash(), "payload_sha256": hash(),
		"producer_profile": map[string]any{"enum": model.List("declared-command/0.1.0", QualifiedCommandProfile, CodexReviewProfile, ClaudeReviewProfile, "host-user-prompt/0.1.0", PairProfile, SMARTSProfile)},
		"producer_run_id":  text(), "producer_result_sha256": hash(),
	}
	required := []string{"format", "kind", "subject", "context_ref", "context_sha256", "payload_sha256", "producer_profile", "producer_run_id", "producer_result_sha256"}
	if current {
		profiles := model.M(base["producer_profile"])
		profiles["enum"] = append(model.A(profiles["enum"]), CodexNativeV1ReviewProfile)
		base["producer_result"] = map[string]any{"oneOf": []any{verificationResultSchema(false), verificationResultSchema(true), reviewResultSchema(), claudeReviewResultSchema(), codexNativeV1ReviewResultSchema(), promptResultSchema(), smartsResultSchema()}}
		required = append(required, "producer_result")
	}
	return closed(base, required...)
}
func Schema() map[string]any { return observationSchema("codearbiter.observation/0.2.0", true) }
func InspectionSchema() map[string]any {
	return map[string]any{"oneOf": []any{observationSchema("codearbiter.observation/0.1.0", false), Schema()}}
}

func ContextRef(sha string) string { return root + "/evidence-contexts/" + sha + ".json" }
func Ref(sha string) string        { return root + "/observations/" + sha + ".json" }

func refHash(p, sub string) (string, error) {
	if path.Dir(p) != root+"/"+sub || !strings.HasSuffix(p, ".json") {
		return "", fault.New("OBSERVATION_UNVERIFIED", "observation locator is outside its content-addressed store")
	}
	h := strings.TrimSuffix(path.Base(p), ".json")
	if !digest.MatchString(h) {
		return "", fault.New("OBSERVATION_UNVERIFIED", "observation locator is not content addressed")
	}
	return h, nil
}

func load(f *store.FS, p, expected, sub string, contract map[string]any) (map[string]any, []byte, error) {
	h, err := refHash(p, sub)
	if err != nil || h != expected {
		return nil, nil, fault.New("OBSERVATION_UNVERIFIED", "observation locator and digest do not agree")
	}
	b, err := f.Read(p, canonical.MaxBytes)
	if err != nil || canonical.BytesHash(b) != expected {
		return nil, nil, fault.New("OBSERVATION_UNVERIFIED", "observation bytes are unavailable or changed")
	}
	v, err := canonical.Object(b)
	if err != nil {
		return nil, nil, fault.New("OBSERVATION_UNVERIFIED", "observation bytes are not canonical JSON")
	}
	if es := schema.ValidateWith(contract, v); len(es) > 0 {
		return nil, nil, &es[0]
	}
	return v, b, nil
}

func LoadContext(f *store.FS, p, expected string) (map[string]any, []byte, error) {
	return load(f, p, expected, "evidence-contexts", ContextSchema())
}
func Inspect(f *store.FS, p, expected string) (map[string]any, []byte, error) {
	return load(f, p, expected, "observations", InspectionSchema())
}
func Load(f *store.FS, p, expected string) (map[string]any, []byte, error) {
	v, b, err := Inspect(f, p, expected)
	if err != nil {
		return nil, nil, err
	}
	if model.S(v["format"]) != "codearbiter.observation/0.2.0" {
		return nil, nil, fault.New("OBSERVATION_UNVERIFIED", "legacy observation remains inspectable but cannot confer authority")
	}
	return v, b, nil
}

// ValidateLink proves that the retained observation identifies exactly the
// event payload and engine-issued context. It never derives a successful
// verdict; that remains the closed host producer's responsibility.
func ValidateLink(event, observed, context map[string]any, contextRef, contextHash string) error {
	fail := func() error {
		return fault.New("OBSERVATION_UNVERIFIED", "observation does not match the authority event and engine context")
	}
	if model.S(observed["kind"]) != model.S(event["kind"]) || model.S(observed["context_ref"]) != contextRef || model.S(observed["context_sha256"]) != contextHash {
		return fail()
	}
	a, _ := canonical.Hash(observed["subject"])
	b, _ := canonical.Hash(event["subject"])
	if a != b {
		return fail()
	}
	payloadHash, _ := canonical.Hash(event["payload"])
	if model.S(observed["payload_sha256"]) != payloadHash {
		return fail()
	}
	if model.S(observed["format"]) == "codearbiter.observation/0.2.0" {
		producerHash, err := canonical.Hash(observed["producer_result"])
		if err != nil || model.S(observed["producer_result_sha256"]) != producerHash {
			return fail()
		}
	}
	kind, profile := model.S(event["kind"]), model.S(observed["producer_profile"])
	if kind == "verification" && profile != "declared-command/0.1.0" && profile != QualifiedCommandProfile || (kind == "spec_review" || kind == "quality_review") && profile != CodexReviewProfile && profile != ClaudeReviewProfile && profile != CodexNativeV1ReviewProfile || (kind == "approval" || kind == "prerequisite" || kind == "reconciliation" || kind == "farm_authorization") && profile != "host-user-prompt/0.1.0" && !(kind == "approval" && (profile == PairProfile || profile == SMARTSProfile)) {
		return fail()
	}
	contextBytes, _ := canonical.Marshal(context)
	if canonical.BytesHash(contextBytes) != contextHash || model.S(context["activity"]) != kind {
		return fail()
	}
	c, _ := canonical.Hash(context["subject"])
	if c != b {
		return fail()
	}
	if model.S(observed["format"]) == "codearbiter.observation/0.2.0" {
		if profile == PairProfile {
			if !validatePairPrompt(observed, event, context) {
				return fail()
			}
		} else if profile == SMARTSProfile {
			if !validateSMARTS(observed, event, context) {
				return fail()
			}
		} else if kind == "verification" {
			if !validateVerification(observed, event, context) {
				return fail()
			}
		} else if kind == "spec_review" || kind == "quality_review" {
			if !validateReview(observed, event, context) {
				return fail()
			}
		} else if !validatePrompt(observed, event, context) {
			return fail()
		}
	}
	return nil
}
func validatePrompt(observed, event, context map[string]any) bool {
	result, payload := model.M(observed["producer_result"]), model.M(event["payload"])
	promptHash := canonical.BytesHash([]byte(model.S(event["source_text"])))
	if model.S(context["prompt_sha256"]) != promptHash || model.S(result["prompt_sha256"]) != promptHash || model.S(observed["producer_run_id"]) != model.S(result["host"])+":"+model.S(result["session_id"]) {
		return false
	}
	kind := model.S(event["kind"])
	if model.S(event["authority_kind"]) != "user_workflow" {
		return false
	}
	if kind == "approval" {
		return len(payload) == 0
	}
	if kind == "prerequisite" {
		return same(payload["prerequisite"], context["record"])
	}
	if model.S(payload["input_sha256"]) != model.S(context["input_sha256"]) {
		return false
	}
	if kind == "farm_authorization" {
		return model.S(payload["input_sha256"]) == model.S(context["input_sha256"])
	}
	if _, task := payload["task_sha256"]; task {
		return model.S(payload["task_sha256"]) == model.S(context["record_sha256"])
	}
	return model.S(payload["assessment"]) != ""
}

func same(a, b any) bool { x, _ := canonical.Hash(a); y, _ := canonical.Hash(b); return x == y }
func validateVerification(observed, event, context map[string]any) bool {
	result, payload := model.M(observed["producer_result"]), model.M(event["payload"])
	for _, field := range []string{"input_sha256", "spec_sha256", "task_sha256"} {
		if model.S(payload[field]) != model.S(context[field]) {
			return false
		}
	}
	commands, bindings, definitions := model.A(result["commands"]), model.A(result["command_bindings"]), model.A(context["commands"])
	if !same(commands, payload["commands"]) || len(commands) != len(bindings) || len(commands) != len(definitions) {
		return false
	}
	before, after := model.A(result["workspace_before"]), model.A(result["workspace_after"])
	if !same(before, after) {
		return false
	}
	workspaces := map[string]map[string]any{}
	for _, value := range before {
		workspace := model.M(value)
		root := model.S(workspace["root"])
		if root == "" || workspaces[root] != nil {
			return false
		}
		workspaces[root] = workspace
	}
	for i := range bindings {
		binding, definitionRow := model.M(bindings[i]), model.M(definitions[i])
		definition := model.M(definitionRow["definition"])
		command := model.M(commands[i])
		if model.S(binding["definition_sha256"]) != model.S(definitionRow["definition_sha256"]) || model.S(command["definition_sha256"]) != model.S(definitionRow["definition_sha256"]) || model.I(command["exit"]) != model.I(definition["expected_exit"]) {
			return false
		}
		required, observedTests := model.Strings(definition["required_tests"]), model.A(command["tests"])
		if len(required) != len(observedTests) {
			return false
		}
		tests := map[string]bool{}
		for _, value := range observedTests {
			name := model.S(model.M(value)["name"])
			if name == "" || tests[name] {
				return false
			}
			tests[name] = true
		}
		for _, name := range required {
			if !tests[name] {
				return false
			}
		}
		if model.S(observed["producer_profile"]) == QualifiedCommandProfile {
			if !validateQualifiedBinding(binding, definition) {
				return false
			}
		} else {
			// Retained legacy evidence cannot be relabelled with the new producer's fields.
			if _, ok := binding["collector_profile"]; ok {
				return false
			}
			if _, ok := binding["launch_files"]; ok {
				return false
			}
			argv, declared := model.Strings(binding["argv"]), model.Strings(definition["argv"])
			if len(argv) != len(declared) || len(argv) == 0 || !filepath.IsAbs(argv[0]) || !same(argv[1:], declared[1:]) {
				return false
			}
		}
		workspace := workspaces[model.S(binding["workspace_root"])]
		if workspace == nil || model.S(workspace["filesystem_id"]) != model.S(binding["workspace_filesystem_id"]) || model.S(workspace["git_common_dir"]) != model.S(binding["git_common_dir"]) || model.S(workspace["git_common_filesystem_id"]) != model.S(binding["git_common_filesystem_id"]) {
			return false
		}
	}
	return true
}
func reviewCoverage(context map[string]any) []string {
	seen := map[string]bool{}
	records := model.A(context["tasks"])
	if model.S(context["activity"]) == "spec_review" {
		records = []any{context["task"]}
	}
	for _, value := range records {
		for _, ref := range model.Strings(model.M(value)["criterion_refs"]) {
			if ref != "" {
				seen[ref] = true
			}
		}
	}
	out := make([]string, 0, len(seen))
	for ref := range seen {
		out = append(out, ref)
	}
	sort.Strings(out)
	return out
}
func reviewContractHash() string {
	contract := map[string]any{"format": "codearbiter.review-decision/0.1.0", "decision": model.List("pass", "changes_requested"), "finding_severity": model.List("BLOCK", "WARN", "INFO"), "required_fields": model.List("format", "request_id", "target_sha256", "contract_sha256", "decision", "coverage", "findings", "assessment")}
	h, _ := canonical.Hash(contract)
	return h
}
func validateReview(observed, event, context map[string]any) bool {
	result, payload := model.M(observed["producer_result"]), model.M(event["payload"])
	launch, decision := model.M(result["launch"]), model.M(result["decision"])
	// The closed oneOf admits each producer's launch shape; bind it to the
	// declared profile so evidence cannot be relabelled across hosts or versions.
	_, codexShape := launch["parent_turn_id"]
	_, claudeShape := launch["parent_prompt_id"]
	_, nativeV1Shape := launch["codex_review_profile"]
	switch model.S(observed["producer_profile"]) {
	case CodexReviewProfile:
		if !codexShape || claudeShape || nativeV1Shape {
			return false
		}
	case CodexNativeV1ReviewProfile:
		if !codexShape || claudeShape || model.S(launch["codex_review_profile"]) != CodexNativeV1ReviewProfile || model.S(launch["child_turn_id"]) == model.S(launch["parent_turn_id"]) {
			return false
		}
	case ClaudeReviewProfile:
		if !claudeShape || codexShape || model.S(launch["agent_type"]) != ClaudeReviewer || model.S(launch["subagent_type"]) != ClaudeReviewer || launch["first_stop"] != true || launch["post_confirmed"] != true {
			return false
		}
	default:
		return false
	}
	if model.S(observed["producer_run_id"]) != model.S(launch["agent_id"]) || model.S(decision["target_sha256"]) != model.S(context["input_sha256"]) || model.S(decision["contract_sha256"]) != reviewContractHash() || model.S(decision["assessment"]) != model.S(payload["assessment"]) {
		return false
	}
	want, got := reviewCoverage(context), model.Strings(decision["coverage"])
	if len(want) != len(got) {
		return false
	}
	sort.Strings(got)
	for i := range want {
		if want[i] != got[i] {
			return false
		}
	}
	for _, value := range model.A(decision["findings"]) {
		if model.S(model.M(value)["severity"]) == "BLOCK" {
			return false
		}
	}
	return len(want) > 0
}
