package observation

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"regexp"
	"strings"
)

const PairProfile = "host-user-pair/0.1.0"
const SMARTSProfile = "smarts-plan-method/0.1.0"

var Lenses = []string{"Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable"}

func pairIdentity(kind string) map[string]any {
	return closed(map[string]any{"artifact_id": text(), "kind": map[string]any{"const": kind}, "revision": map[string]any{"type": "integer", "minimum": int64(1)}, "model_sha256": hash(), "normative_sha256": hash()}, "artifact_id", "kind", "revision", "model_sha256", "normative_sha256")
}

// PairSchema freezes both drafts and the deterministic approved-source binding.
// Delegation must be visible in the actual host-observed reply.
func PairSchema() map[string]any {
	return closed(map[string]any{"format": map[string]any{"const": "codearbiter.sprint-pair/0.1.0"}, "spec": pairIdentity("spec"), "plan": pairIdentity("plan"), "approved_plan_normative_sha256": hash(), "scope_sha256": hash(), "delegate_methods": map[string]any{"type": "boolean"}}, "format", "spec", "plan", "approved_plan_normative_sha256", "scope_sha256", "delegate_methods")
}
func boundedText(max int64) map[string]any {
	return map[string]any{"type": "string", "minLength": int64(1), "maxLength": max}
}
func DecisionSchema() map[string]any {
	lenses := map[string]any{}
	for _, name := range Lenses {
		lenses[name] = closed(map[string]any{"verdict": map[string]any{"enum": model.List("Strong", "Adequate", "Weak", "Indifferent")}, "reason": boundedText(400)}, "verdict", "reason")
	}
	option := closed(map[string]any{"label": boundedText(160), "steps": map[string]any{"type": "array", "minItems": int64(1), "maxItems": int64(32), "uniqueItems": true, "items": boundedText(2000)}, "lenses": closed(lenses, Lenses...)}, "label", "steps", "lenses")
	return closed(map[string]any{"task_id": text(), "options": map[string]any{"type": "array", "minItems": int64(1), "maxItems": int64(8), "items": option}, "selected": map[string]any{"type": "integer", "minimum": int64(0), "maximum": int64(7)}, "strength": map[string]any{"enum": model.List("strong", "moderate", "tied")}, "rationale": boundedText(4000)}, "task_id", "options", "selected", "strength", "rationale")
}
func SMARTSRecordSchema() map[string]any {
	return closed(map[string]any{"pair": PairSchema(), "grant_receipt": text(), "decision": DecisionSchema(), "before_normative": map[string]any{"type": "object"}, "after_normative": map[string]any{"type": "object"}}, "pair", "grant_receipt", "decision", "before_normative", "after_normative")
}
func smartsResultSchema() map[string]any {
	return closed(map[string]any{"grant_receipt": text(), "decision_sha256": hash(), "scope_sha256": hash()}, "grant_receipt", "decision_sha256", "scope_sha256")
}

var hedging = regexp.MustCompile(`(?i)\b(potentially|might|arguably|perhaps|generally|tends to|could be|may)\b`)
var pairToken = regexp.MustCompile(`^[A-Za-z0-9_-]{12,128}$`)

// ValidateDecision validates the existing qualitative vocabulary and comparison,
// not the truth of a model's assessment. Ties inside delegation are allowed.
// There is no invented numerical threshold or compulsory extra alternative.
func ValidateDecision(d map[string]any) error {
	if es := schema.ValidateWith(DecisionSchema(), d); len(es) > 0 {
		return &es[0]
	}
	options := model.A(d["options"])
	selected := model.I(d["selected"])
	if selected >= int64(len(options)) {
		return fault.New("INVALID_SMARTS", "selected option is absent")
	}
	labels := map[string]bool{}
	for _, v := range options {
		o := model.M(v)
		label := model.S(o["label"])
		if labels[label] {
			return fault.New("INVALID_SMARTS", "options must have distinct labels")
		}
		labels[label] = true
		for _, name := range Lenses {
			c := model.M(model.M(o["lenses"])[name])
			reason := model.S(c["reason"])
			if len(strings.Fields(reason)) > 20 || hedging.MatchString(reason) {
				return fault.New("INVALID_SMARTS", "lens justification exceeds its budget or contains prohibited hedging")
			}
		}
	}
	choice := model.M(model.M(options[selected])["lenses"])
	rank := map[string]int{"Weak": 0, "Adequate": 1, "Strong": 2}
	for i, v := range options {
		if int64(i) == selected {
			continue
		}
		noWorse, better := true, false
		for _, name := range Lenses {
			a := model.S(model.M(model.M(model.M(v)["lenses"])[name])["verdict"])
			b := model.S(model.M(choice[name])["verdict"])
			if a == b {
				continue
			}
			ra, oka := rank[a]
			rb, okb := rank[b]
			if !oka || !okb || ra < rb {
				noWorse = false
			}
			if oka && okb && ra > rb {
				better = true
			}
		}
		if noWorse && better {
			return fault.New("INVALID_SMARTS", "selected option is dominated by its own recorded comparison")
		}
	}
	return nil
}

// ProtectedPlanHash excludes ONLY existing task method steps. It retains every
// criterion, path, prerequisite, verification command, rollback, input and
// checkpoint. Approving steps cannot confer runtime or publication permission.
func ProtectedPlanHash(norm map[string]any) (string, error) {
	copy, err := canonical.Clone(norm)
	if err != nil {
		return "", err
	}
	for _, v := range model.A(copy["tasks"]) {
		delete(model.M(v), "steps")
	}
	return canonical.Hash(copy)
}
func ValidateSMARTSRecord(record map[string]any) error {
	if es := schema.ValidateWith(SMARTSRecordSchema(), record); len(es) > 0 {
		return &es[0]
	}
	pair := model.M(record["pair"])
	if pair["delegate_methods"] != true {
		return fault.New("DELEGATION_REQUIRED", "initial reply did not delegate plan-method decisions")
	}
	decision := model.M(record["decision"])
	if err := ValidateDecision(decision); err != nil {
		return err
	}
	before, after := model.M(record["before_normative"]), model.M(record["after_normative"])
	for _, n := range []map[string]any{before, after} {
		h, err := ProtectedPlanHash(n)
		if err != nil || h != model.S(pair["scope_sha256"]) {
			return fault.New("DELEGATION_SCOPE", "decision changes the user-approved protected scope")
		}
	}
	projected, err := canonical.Clone(before)
	if err != nil {
		return err
	}
	found := false
	steps := model.M(model.A(decision["options"])[model.I(decision["selected"])])["steps"]
	for _, v := range model.A(projected["tasks"]) {
		t := model.M(v)
		if model.S(t["id"]) == model.S(decision["task_id"]) {
			t["steps"] = steps
			found = true
		}
	}
	if !found || !same(projected, after) {
		return fault.New("DELEGATION_SCOPE", "only the selected existing task's method steps may change")
	}
	return nil
}
func validatePairPrompt(observed, event, context map[string]any) bool {
	payload := model.M(event["payload"])
	pair := model.M(payload["sprint_pair"])
	if len(payload) != 1 || len(schema.ValidateWith(PairSchema(), pair)) != 0 || !same(context["record"], payload) {
		return false
	}
	h, _ := canonical.Hash(payload)
	if model.S(context["record_sha256"]) != h {
		return false
	}
	if model.S(event["kind"]) != "approval" || model.S(event["authority_kind"]) != "user_workflow" {
		return false
	}
	result := model.M(observed["producer_result"])
	prompt := model.S(event["source_text"])
	ph := canonical.BytesHash([]byte(prompt))
	if model.S(context["prompt_sha256"]) != ph || model.S(result["prompt_sha256"]) != ph || model.S(observed["producer_run_id"]) != model.S(result["host"])+":"+model.S(result["session_id"]) {
		return false
	}
	spec, plan := model.M(pair["spec"]), model.M(pair["plan"])
	parts := strings.Split(prompt, " ")
	mode := "approve-only"
	if pair["delegate_methods"] == true {
		mode = "delegate-methods"
	}
	if len(parts) != 5 || parts[0] != "approve-sprint" || parts[1] != model.S(spec["artifact_id"]) || parts[2] != model.S(plan["artifact_id"]) || parts[3] != mode || !pairToken.MatchString(parts[4]) {
		return false
	}
	subject := model.M(event["subject"])
	id := model.S(subject["artifact_id"])
	want := model.S(spec["normative_sha256"])
	if id == model.S(plan["artifact_id"]) {
		want = model.S(pair["approved_plan_normative_sha256"])
	} else if id != model.S(spec["artifact_id"]) {
		return false
	}
	return model.S(subject["record_id"]) == id && model.S(subject["normative_sha256"]) == want && model.S(context["input_sha256"]) == want
}
func validateSMARTS(observed, event, context map[string]any) bool {
	payload := model.M(event["payload"])
	record := model.M(payload["smarts"])
	if len(payload) != 1 || ValidateSMARTSRecord(record) != nil || !same(context["record"], payload) {
		return false
	}
	ph, _ := canonical.Hash(payload)
	if model.S(context["record_sha256"]) != ph {
		return false
	}
	if model.S(event["kind"]) != "approval" || model.S(event["authority_kind"]) != "smarts_workflow" || model.S(event["origin"]) != model.S(observed["producer_run_id"]) {
		return false
	}
	pair := model.M(record["pair"])
	result := model.M(observed["producer_result"])
	dh, _ := canonical.Hash(record["decision"])
	id := model.S(model.M(pair["plan"])["artifact_id"])
	afterHash, _ := canonical.Hash(map[string]any{"format_version": model.FormatVersion, "kind": "plan", "schema_version": model.SchemaVersion, "artifact_id": id, "normative": record["after_normative"]})
	subject := model.M(event["subject"])
	decisionBytes, _ := canonical.Marshal(record["decision"])
	return model.S(result["grant_receipt"]) == model.S(record["grant_receipt"]) && model.S(result["decision_sha256"]) == dh && model.S(result["scope_sha256"]) == model.S(pair["scope_sha256"]) && model.S(subject["artifact_id"]) == id && model.S(subject["record_id"]) == id && model.S(subject["normative_sha256"]) == afterHash && model.S(context["input_sha256"]) == afterHash && model.S(event["source_text"]) == string(decisionBytes) && model.S(context["prompt_sha256"]) == canonical.BytesHash(decisionBytes)
}
