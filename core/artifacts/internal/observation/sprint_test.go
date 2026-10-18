package observation

import (
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// --- smarts-plan-method/0.2.0 decision fixtures -----------------------

func cellV2(verdict, reason string) map[string]any {
	return map[string]any{"verdict": verdict, "reason": reason}
}

func unknownCellV2(reason, missing string, critical bool) map[string]any {
	return map[string]any{"verdict": "Unknown", "reason": reason, "missing_observation": missing, "decision_critical": critical}
}

// baselineLensesV2 returns an "Adequate" cell for every lens, with any
// named overrides applied on top.
func baselineLensesV2(overrides map[string]map[string]any) map[string]any {
	out := map[string]any{}
	for _, name := range Lenses {
		if c, ok := overrides[name]; ok {
			out[name] = c
		} else {
			out[name] = cellV2("Adequate", "Fine baseline fit.")
		}
	}
	return out
}

func optionV2(label string, lenses map[string]any) map[string]any {
	return map[string]any{"label": label, "steps": []any{"Do the work."}, "lenses": lenses}
}

func decisionV2(options []any, selected int64, strength string) map[string]any {
	return map[string]any{"task_id": "T-001", "options": options, "selected": selected, "strength": strength, "rationale": "Chosen for balanced tradeoffs."}
}

func twoOptionDecisionV2(selectedLenses, otherLenses map[string]any, selected int64, strength string) map[string]any {
	options := []any{optionV2("Option A", selectedLenses), optionV2("Option B", otherLenses)}
	// Keep labels distinct regardless of which index is selected.
	return decisionV2(options, selected, strength)
}

func assertInvalidSmarts(t *testing.T, err error, substr string) {
	t.Helper()
	if err == nil {
		t.Fatal("expected rejection, got nil error")
	}
	if fault.Code(err) != "INVALID_SMARTS" {
		t.Fatalf("expected INVALID_SMARTS, got %s: %v", fault.Code(err), err)
	}
	if !strings.Contains(err.Error(), substr) {
		t.Fatalf("expected error to mention %q, got: %v", substr, err)
	}
}

func assertInvalidModel(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		t.Fatal("expected rejection, got nil error")
	}
	if fault.Code(err) != "INVALID_MODEL" {
		t.Fatalf("expected INVALID_MODEL (schema rejection), got %s: %v", fault.Code(err), err)
	}
}

func TestSMARTSDecisionUnknownRequiresFields(t *testing.T) {
	// Negative: an Unknown cell missing both required fields is rejected by
	// the schema, not a Go-level check.
	bad := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Unknown", "reason": "Needs clarity."},
	})
	d := twoOptionDecisionV2(bad, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d))

	// Negative: decision_critical present but missing_observation absent.
	bad2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Unknown", "reason": "Needs clarity.", "decision_critical": false},
	})
	d2 := twoOptionDecisionV2(bad2, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d2))

	// Negative: missing_observation present but decision_critical absent.
	// Read as false, an absent flag would let a critical Unknown be selected.
	bad3 := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Unknown", "reason": "Needs clarity.", "missing_observation": "A load test under real traffic."},
	})
	d4 := twoOptionDecisionV2(bad3, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d4))

	// Positive: both required fields present on an Unknown cell, decision
	// otherwise valid, passes.
	good := baselineLensesV2(map[string]map[string]any{
		"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
	})
	d3 := twoOptionDecisionV2(good, baselineLensesV2(nil), 0, "moderate")
	if err := ValidateDecisionV2(d3); err != nil {
		t.Fatalf("valid Unknown cell rejected: %v", err)
	}
}

func TestSMARTSDecisionUnknownFieldsForbiddenElsewhere(t *testing.T) {
	// Negative: a non-Unknown verdict carrying the Unknown-only fields is
	// rejected by the schema.
	bad := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Strong", "reason": "Handles growth well.", "missing_observation": "A load test.", "decision_critical": false},
	})
	d := twoOptionDecisionV2(bad, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d))

	// Negative: decision_critical alone on a Strong cell.
	bad2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Strong", "reason": "Handles growth well.", "decision_critical": true},
	})
	d2 := twoOptionDecisionV2(bad2, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d2))

	// Negative: missing_observation alone on a Strong cell.
	bad3 := baselineLensesV2(map[string]map[string]any{
		"Scalable": {"verdict": "Strong", "reason": "Handles growth well.", "missing_observation": "A load test."},
	})
	d4 := twoOptionDecisionV2(bad3, baselineLensesV2(nil), 0, "moderate")
	assertInvalidModel(t, ValidateDecisionV2(d4))

	// Positive: an ordinary cell with neither field is fine.
	d3 := twoOptionDecisionV2(baselineLensesV2(nil), baselineLensesV2(nil), 0, "moderate")
	if err := ValidateDecisionV2(d3); err != nil {
		t.Fatalf("valid decision with no Unknown cells rejected: %v", err)
	}
}

func TestSMARTSDecisionIndifferentIsUniform(t *testing.T) {
	// Negative: one option marks a lens Indifferent, the other does not.
	selected := baselineLensesV2(map[string]map[string]any{
		"Scalable": cellV2("Indifferent", "Does not affect scale."),
	})
	other := baselineLensesV2(nil)
	d := twoOptionDecisionV2(selected, other, 0, "moderate")
	assertInvalidSmarts(t, ValidateDecisionV2(d), "uniform")

	// Negative: only the compared option marks the lens Indifferent.
	other3 := baselineLensesV2(map[string]map[string]any{
		"Scalable": cellV2("Indifferent", "Does not affect scale."),
	})
	d3 := twoOptionDecisionV2(baselineLensesV2(nil), other3, 0, "moderate")
	assertInvalidSmarts(t, ValidateDecisionV2(d3), "uniform")

	// Positive: both options mark the same lens Indifferent.
	selected2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": cellV2("Indifferent", "Does not affect scale."),
	})
	other2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": cellV2("Indifferent", "Does not affect scale."),
	})
	d2 := twoOptionDecisionV2(selected2, other2, 0, "moderate")
	if err := ValidateDecisionV2(d2); err != nil {
		t.Fatalf("uniform Indifferent lens rejected: %v", err)
	}
}

func TestSMARTSDecisionCriticalUnknownBlocksSelection(t *testing.T) {
	// Negative: the SELECTED option carries a decision-critical Unknown.
	selected := baselineLensesV2(map[string]map[string]any{
		"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", true),
	})
	other := baselineLensesV2(nil)
	d := twoOptionDecisionV2(selected, other, 0, "moderate")
	assertInvalidSmarts(t, ValidateDecisionV2(d), "selected option carries a decision-critical unknown")

	// Positive: same shape, but the Unknown is not decision-critical.
	selected2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
	})
	d2 := twoOptionDecisionV2(selected2, other, 0, "moderate")
	if err := ValidateDecisionV2(d2); err != nil {
		t.Fatalf("non-critical Unknown on selected option rejected: %v", err)
	}
}

func TestSMARTSDecisionStrongRefusedWithCriticalUnknown(t *testing.T) {
	// Negative: the NON-selected option carries a decision-critical Unknown
	// and strength is strong.
	selected := baselineLensesV2(nil)
	other := baselineLensesV2(map[string]map[string]any{
		"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", true),
	})
	d := twoOptionDecisionV2(selected, other, 0, "strong")
	assertInvalidSmarts(t, ValidateDecisionV2(d), "strength cannot be strong")

	// Positive: identical decision but strength moderate passes.
	d2 := twoOptionDecisionV2(selected, other, 0, "moderate")
	if err := ValidateDecisionV2(d2); err != nil {
		t.Fatalf("moderate strength with a non-selected critical unknown rejected: %v", err)
	}

	// Positive: identical decision but the Unknown is not decision-critical,
	// strength strong passes.
	other2 := baselineLensesV2(map[string]map[string]any{
		"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
	})
	d3 := twoOptionDecisionV2(selected, other2, 0, "strong")
	if err := ValidateDecisionV2(d3); err != nil {
		t.Fatalf("strong strength with a non-critical unknown rejected: %v", err)
	}
}

func TestSMARTSDecisionUnknownCannotShieldDominatedChoice(t *testing.T) {
	t.Run("selected non-critical Unknown does not shield domination", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{
			"Scalable":     unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
			"Maintainable": cellV2("Weak", "Hard to extend later."),
		})
		other := baselineLensesV2(map[string]map[string]any{
			"Maintainable": cellV2("Strong", "Simple to extend later."),
		})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "dominated")
	})

	t.Run("selected Unknown against a compared Strong is dominated (SCN-04-01)", func(t *testing.T) {
		// The ONLY difference between the options is selected Unknown versus
		// compared Strong on one lens; every other lens is equal.
		selected := baselineLensesV2(map[string]map[string]any{
			"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
		})
		other := baselineLensesV2(map[string]map[string]any{
			"Scalable": cellV2("Strong", "Handles growth well."),
		})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "dominated")
	})

	t.Run("selected Unknown against a compared Strong is not dominated across a tradeoff", func(t *testing.T) {
		// The selected option is better on another lens, so the compared
		// option is not no-worse everywhere and cannot dominate.
		selected := baselineLensesV2(map[string]map[string]any{
			"Scalable":     unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
			"Maintainable": cellV2("Strong", "Simple to extend later."),
		})
		other := baselineLensesV2(map[string]map[string]any{
			"Scalable": cellV2("Strong", "Handles growth well."),
		})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		if err := ValidateDecisionV2(d); err != nil {
			t.Fatalf("a tradeoff must not be reported as domination: %v", err)
		}
	})

	t.Run("compared option's Unknown cannot prove domination", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{
			"Scalable":     cellV2("Strong", "Handles growth well."),
			"Maintainable": cellV2("Weak", "Hard to extend later."),
		})
		other := baselineLensesV2(map[string]map[string]any{
			"Scalable":     unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
			"Maintainable": cellV2("Strong", "Simple to extend later."),
		})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		if err := ValidateDecisionV2(d); err != nil {
			t.Fatalf("an Unknown on the compared option must not prove domination: %v", err)
		}
	})

	t.Run("more Strong cells elsewhere do not outweigh a tradeoff (AC-06)", func(t *testing.T) {
		// AC-06: dominance is ordinal per lens, never a cell count. The compared
		// option has three Strong cells to the selected option's one but is worse
		// on Securable, so it cannot dominate and the selection stands under
		// both the 0.2.0 and the 0.1.0 validator.
		selected := baselineLensesV2(map[string]map[string]any{"Securable": cellV2("Strong", "Default-deny at every boundary.")})
		other := baselineLensesV2(map[string]map[string]any{
			"Scalable":     cellV2("Strong", "Handles growth well."),
			"Maintainable": cellV2("Strong", "Simple to extend later."),
			"Available":    cellV2("Strong", "Survives one host outage."),
			"Securable":    cellV2("Weak", "Exposes an unauthenticated port."),
		})
		for name, validate := range map[string]func(map[string]any) error{"0.2.0": ValidateDecisionV2, "0.1.0": ValidateDecision} {
			if err := validate(twoOptionDecisionV2(selected, other, 0, "moderate")); err != nil {
				t.Fatalf("%s: a tradeoff must not lose to a cell count: %v", name, err)
			}
		}
	})

	t.Run("Unknown versus Unknown on the same lens is neutral", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{
			"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
		})
		other := baselineLensesV2(map[string]map[string]any{
			"Scalable": unknownCellV2("Needs clarity.", "A load test under real traffic.", false),
		})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		if err := ValidateDecisionV2(d); err != nil {
			t.Fatalf("matching Unknown verdicts on both options must be neutral: %v", err)
		}
	})
}

// TestSMARTSDecisionV2KeepsRetainedRejections pins AC-15: under
// smarts-plan-method/0.2.0 the validator still rejects every malformed
// decision the 0.1.0 validator rejects.
func TestSMARTSDecisionV2KeepsRetainedRejections(t *testing.T) {
	t.Run("valid baseline is accepted", func(t *testing.T) {
		d := twoOptionDecisionV2(baselineLensesV2(nil), baselineLensesV2(nil), 0, "tied")
		if err := ValidateDecisionV2(d); err != nil {
			t.Fatalf("baseline must validate: %v", err)
		}
	})
	t.Run("hedging is rejected", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{"Reliable": cellV2("Adequate", "It might recover cleanly.")})
		d := twoOptionDecisionV2(selected, baselineLensesV2(nil), 0, "tied")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "hedging")
	})
	t.Run("hedging in an Unknown reason is rejected", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{"Reliable": unknownCellV2("Perhaps fine.", "A failover drill.", false)})
		d := twoOptionDecisionV2(selected, baselineLensesV2(nil), 0, "tied")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "hedging")
	})
	t.Run("over-budget justification is rejected", func(t *testing.T) {
		long := strings.TrimSpace(strings.Repeat("word ", 21))
		selected := baselineLensesV2(map[string]map[string]any{"Testable": cellV2("Adequate", long)})
		d := twoOptionDecisionV2(selected, baselineLensesV2(nil), 0, "tied")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "budget")
	})
	t.Run("duplicate labels are rejected", func(t *testing.T) {
		d := decisionV2([]any{optionV2("Same", baselineLensesV2(nil)), optionV2("Same", baselineLensesV2(nil))}, 0, "tied")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "distinct labels")
	})
	t.Run("selected index beyond the options is rejected", func(t *testing.T) {
		d := twoOptionDecisionV2(baselineLensesV2(nil), baselineLensesV2(nil), 5, "tied")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "selected option is absent")
	})
	t.Run("missing lens is rejected", func(t *testing.T) {
		selected := baselineLensesV2(nil)
		delete(selected, "Securable")
		d := twoOptionDecisionV2(selected, baselineLensesV2(nil), 0, "tied")
		assertInvalidModel(t, ValidateDecisionV2(d))
	})
	t.Run("malformed choice is rejected", func(t *testing.T) {
		bad := optionV2("Option A", baselineLensesV2(nil))
		bad["steps"] = []any{}
		d := decisionV2([]any{bad, optionV2("Option B", baselineLensesV2(nil))}, 0, "tied")
		assertInvalidModel(t, ValidateDecisionV2(d))
	})
	t.Run("dominated selection on known verdicts is rejected", func(t *testing.T) {
		selected := baselineLensesV2(map[string]map[string]any{"Available": cellV2("Weak", "Single host outage stops it.")})
		other := baselineLensesV2(map[string]map[string]any{"Available": cellV2("Strong", "Survives one host outage.")})
		d := twoOptionDecisionV2(selected, other, 0, "moderate")
		assertInvalidSmarts(t, ValidateDecisionV2(d), "dominated")
	})
}
