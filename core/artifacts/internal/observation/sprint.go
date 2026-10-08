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

// LegacySMARTSProfile names the four-state smarts-plan-method/0.1.0
// vocabulary explicitly; SMARTSProfile is its historical name. Historical
// records keep validating under it. The smarts-apply producer
// (operations/sprint.go) stamps and validates new records as SMARTSProfileV2.
const LegacySMARTSProfile = SMARTSProfile

// SMARTSProfileV2 is the smarts-plan-method/0.2.0 vocabulary implemented by
// DecisionSchemaV2 and ValidateDecisionV2 below. The observation contract
// admits both profiles and ValidateSMARTSRecordFor routes each recorded
// producer_profile to its own schema and validator; any other profile fails
// closed.
const SMARTSProfileV2 = "smarts-plan-method/0.2.0"

// IsSMARTSProfile reports whether profile is a SMARTS plan-method producer
// profile the engine validates.
func IsSMARTSProfile(profile string) bool {
	return profile == LegacySMARTSProfile || profile == SMARTSProfileV2
}

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

// cellSchemaV2 is the smarts-plan-method/0.2.0 lens cell: the Unknown
// verdict carries two additional REQUIRED fields (missing_observation,
// decision_critical) that no other verdict may carry. oneOf enforces both
// directions in the schema itself; Go code never duplicates this check.
func cellSchemaV2() map[string]any {
	known := closed(map[string]any{"verdict": map[string]any{"enum": model.List("Strong", "Adequate", "Weak", "Indifferent")}, "reason": boundedText(400)}, "verdict", "reason")
	unknown := closed(map[string]any{"verdict": map[string]any{"const": "Unknown"}, "reason": boundedText(400), "missing_observation": boundedText(400), "decision_critical": map[string]any{"type": "boolean"}}, "verdict", "reason", "missing_observation", "decision_critical")
	return map[string]any{"oneOf": []any{known, unknown}}
}

// DecisionSchemaV2 is the smarts-plan-method/0.2.0 vocabulary: Strong,
// Adequate, Weak, Indifferent, Unknown. It does not replace DecisionSchema,
// which remains the smarts-plan-method/0.1.0 four-state schema; historical
// 0.1.0 records keep validating under it.
func DecisionSchemaV2() map[string]any {
	cell := cellSchemaV2()
	lenses := map[string]any{}
	for _, name := range Lenses {
		lenses[name] = cell
	}
	option := closed(map[string]any{"label": boundedText(160), "steps": map[string]any{"type": "array", "minItems": int64(1), "maxItems": int64(32), "uniqueItems": true, "items": boundedText(2000)}, "lenses": closed(lenses, Lenses...)}, "label", "steps", "lenses")
	return closed(map[string]any{"task_id": text(), "options": map[string]any{"type": "array", "minItems": int64(1), "maxItems": int64(8), "items": option}, "selected": map[string]any{"type": "integer", "minimum": int64(0), "maximum": int64(7)}, "strength": map[string]any{"enum": model.List("strong", "moderate", "tied")}, "rationale": boundedText(4000)}, "task_id", "options", "selected", "strength", "rationale")
}

func SMARTSRecordSchema() map[string]any { return smartsRecordSchema(DecisionSchema()) }
func smartsRecordSchema(decision map[string]any) map[string]any {
	return closed(map[string]any{"pair": PairSchema(), "grant_receipt": text(), "decision": decision, "before_normative": map[string]any{"type": "object"}, "after_normative": map[string]any{"type": "object"}}, "pair", "grant_receipt", "decision", "before_normative", "after_normative")
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
	if err := validateChoices(options, selected); err != nil {
		return err
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

func truthy(v any) bool { b, _ := v.(bool); return b }

// validateChoices holds the checks both vocabularies share: the selected
// index exists, labels are distinct, and every lens justification stays
// within the 20-word budget without prohibited hedging.
func validateChoices(options []any, selected int64) error {
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
			reason := model.S(model.M(model.M(o["lenses"])[name])["reason"])
			if len(strings.Fields(reason)) > 20 || hedging.MatchString(reason) {
				return fault.New("INVALID_SMARTS", "lens justification exceeds its budget or contains prohibited hedging")
			}
		}
	}
	return nil
}

// ValidateDecisionV2 validates the smarts-plan-method/0.2.0 vocabulary. It
// keeps every smarts-plan-method/0.1.0 check (missing lenses via schema,
// hedging, the 20-word justification budget, distinct labels, selected-index
// bounds, and per-lens ordinal dominance -- no cell counts, weights, sums,
// percentages or winner arithmetic) and additionally enforces:
//   - Indifferent is uniform: if any option marks a lens Indifferent, every
//     option must mark that lens Indifferent.
//   - A selected option carrying a decision-critical Unknown is rejected.
//   - strength: strong is rejected when ANY option carries a
//     decision-critical Unknown.
//   - Unknown cannot shield a dominated choice: a non-critical Unknown on
//     the SELECTED option counts as no better than the compared option's
//     verdict on that lens (it cannot disable the dominance check the way
//     any unranked verdict used to), and strictly worse than a compared
//     Strong, so that lens alone can prove domination; an Unknown on the COMPARED option means
//     that option cannot be shown to dominate on that lens.
//
// ValidateSMARTSRecordFor routes smarts-plan-method/0.2.0 records here.
func ValidateDecisionV2(d map[string]any) error {
	if es := schema.ValidateWith(DecisionSchemaV2(), d); len(es) > 0 {
		return &es[0]
	}
	options := model.A(d["options"])
	selected := model.I(d["selected"])
	if err := validateChoices(options, selected); err != nil {
		return err
	}
	anyCriticalUnknown := false
	for _, v := range options {
		for _, name := range Lenses {
			c := model.M(model.M(model.M(v)["lenses"])[name])
			if model.S(c["verdict"]) == "Unknown" && truthy(c["decision_critical"]) {
				anyCriticalUnknown = true
			}
		}
	}
	for _, name := range Lenses {
		marked := false
		for _, v := range options {
			if model.S(model.M(model.M(model.M(v)["lenses"])[name])["verdict"]) == "Indifferent" {
				marked = true
			}
		}
		if !marked {
			continue
		}
		for _, v := range options {
			if model.S(model.M(model.M(model.M(v)["lenses"])[name])["verdict"]) != "Indifferent" {
				return fault.New("INVALID_SMARTS", "an indifferent lens verdict must be uniform across every option")
			}
		}
	}
	if model.S(d["strength"]) == "strong" && anyCriticalUnknown {
		return fault.New("INVALID_SMARTS", "strength cannot be strong while any option carries a decision-critical unknown")
	}
	choice := model.M(model.M(options[selected])["lenses"])
	for _, name := range Lenses {
		c := model.M(choice[name])
		if model.S(c["verdict"]) == "Unknown" && truthy(c["decision_critical"]) {
			return fault.New("INVALID_SMARTS", "selected option carries a decision-critical unknown")
		}
	}
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
			if b == "Unknown" {
				// No better than the compared verdict; strictly worse than Strong.
				if a == "Strong" {
					better = true
				}
				continue
			}
			// A compared Unknown is unranked, so it clears noWorse below and
			// that option cannot be shown to dominate on this lens.
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

// ValidateSMARTSRecord validates a record under the four-state
// smarts-plan-method/0.1.0 profile.
func ValidateSMARTSRecord(record map[string]any) error {
	return ValidateSMARTSRecordFor(SMARTSProfile, record)
}

// ValidateSMARTSRecordFor validates a record under the vocabulary of the
// profile it was recorded with: 0.1.0 under the four-state schema, 0.2.0
// under the five-state schema. An unrecognized profile is rejected.
func ValidateSMARTSRecordFor(profile string, record map[string]any) error {
	decisionSchema, validateDecision := DecisionSchema(), ValidateDecision
	switch profile {
	case LegacySMARTSProfile:
	case SMARTSProfileV2:
		decisionSchema, validateDecision = DecisionSchemaV2(), ValidateDecisionV2
	default:
		return fault.New("INVALID_SMARTS", "unrecognized SMARTS producer profile")
	}
	if es := schema.ValidateWith(smartsRecordSchema(decisionSchema), record); len(es) > 0 {
		return &es[0]
	}
	pair := model.M(record["pair"])
	if pair["delegate_methods"] != true {
		return fault.New("DELEGATION_REQUIRED", "initial reply did not delegate plan-method decisions")
	}
	decision := model.M(record["decision"])
	if err := validateDecision(decision); err != nil {
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
	if len(payload) != 1 || ValidateSMARTSRecordFor(model.S(observed["producer_profile"]), record) != nil || !same(context["record"], payload) {
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
