package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"testing"
)

func TestReviewNoZeroTestProofForAlternateRunnerSpelling(t *testing.T) {
	for _, argv := range [][]string{
		{"/usr/local/go/bin/go", "test", "./..."},
		{"python3", "-m", "pytest", "tests"},
		{"npm", "test"},
		{"node", "--test", "test.js"},
	} {
		t.Run(argv[0], func(t *testing.T) {
			s := testutil.Seal(t, testutil.Spec())
			p := testutil.Plan(s)
			task := model.M(model.A(model.M(p["normative"])["tasks"])[0])
			command := model.M(model.A(task["verification"])[0])
			command["argv"] = model.List(argv...)
			command["required_tests"] = model.List()
			d := testutil.Seal(t, p)
			task = d.Symbols.ByID["T-001"].Value
			th, _ := canonical.Hash(task)
			ch, _ := canonical.Hash(command)
			input := canonical.BytesHash([]byte("input"))
			r := &authority.Receipt{
				Data:  map[string]any{"kind": "verification", "subject": map[string]any{"artifact_id": d.ID(), "normative_sha256": d.NormHash(), "record_id": "T-001"}},
				Event: map[string]any{"payload": map[string]any{"input_sha256": input, "spec_sha256": s.NormHash(), "task_sha256": th, "commands": []any{map[string]any{"definition_sha256": ch, "exit": int64(0), "tests": []any{}, "stdout_sha256": canonical.BytesHash(nil), "stderr_sha256": canonical.BytesHash(nil)}}}},
			}
			if err := TaskPayload(r, d, s, task, input); fault.Code(err) != "NO_TESTS_DECLARED" {
				t.Fatalf("zero-test evidence was accepted for %v: %v", argv, err)
			}
		})
	}
}
