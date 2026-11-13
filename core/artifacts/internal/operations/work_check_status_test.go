package operations

// NT-07 / N-F06: work check_status accepts unknown/passed/failed, but no
// implemented native event writes passed or failed. Transition rows: N28:01,
// N29:01-N29:07, N35:01.

import (
	"fmt"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// No request contract of any operation can carry a check status.
func TestNoOperationRequestCanSetWorkCheckStatus(t *testing.T) {
	for _, name := range Names() {
		s, err := RequestSchema(name)
		if err != nil {
			t.Fatal(err)
		}
		b, err := canonical.Marshal(s)
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(b), "check_status") {
			t.Errorf("%s request contract can name a work check status", name)
		}
	}
}

func TestWorkLifecycleNeverManufacturesCheckStatus(t *testing.T) {
	root := testutil.Root(t)
	run := func(op string, r object) object {
		t.Helper()
		r["protocol"] = Protocol
		out, err := Run(root, op, r)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(out)
	}
	created := run("work-create", object{"operation_id": "nt07-create-0001", "title": "Check status witness", "intent": "Keep proof separate", "work_type": "fix"})
	id := model.S(created["work_id"])
	current := created
	n := 1
	for _, action := range []string{"start", "complete", "reopen", "complete", "archive"} {
		n++
		current = run("work-update", object{"operation_id": fmt.Sprintf("nt07-update-%04d", n), "work_id": id,
			"expected": object{"revision": current["revision"], "model_sha256": current["model_sha256"]}, "action": action})
		got := run("work-get", object{"work_id": id})
		if got["check_status"] != "unknown" {
			t.Fatalf("%s manufactured check status %v", action, got["check_status"])
		}
	}
	caps := run("capabilities", object{})
	contract := model.M(caps["operation_contract"])
	var row object
	for _, v := range model.A(contract["schema_only_values"]) {
		if model.M(v)["field"] == "work.execution.check_status" {
			row = model.M(v)
		}
	}
	if row == nil || strings.Join(model.Strings(row["values"]), ",") != "passed,failed" ||
		strings.Join(model.Strings(row["produced_values"]), ",") != "unknown" {
		t.Fatalf("capabilities do not label schema-only check status values: %v", contract["schema_only_values"])
	}
}
