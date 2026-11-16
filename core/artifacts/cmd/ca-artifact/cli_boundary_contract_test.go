package main

// CLI protocol characterization through in-process I/O and owned repositories.
import (
	"bytes"
	"encoding/json"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

type n37FailedOutput struct {
	calls   int
	offered []byte
}

func (w *n37FailedOutput) Write(p []byte) (int, error) {
	w.calls++
	w.offered = append(w.offered, p...)
	return 0, io.ErrClosedPipe
}

func n37CreateRequest(t *testing.T) (map[string]any, []byte) {
	t.Helper()
	normative := model.M(testutil.Spec()["normative"])
	request := map[string]any{
		"protocol": operations.Protocol, "operation_id": "n37-create-once-001",
		"kind": "spec", "artifact_id": "SPEC-EXAMPLE", "slug": "example",
		"title": normative["title"], "summary": normative["summary"], "normative": normative,
	}
	raw, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	return request, raw
}

func n37Envelope(t *testing.T, raw []byte, operation string, success bool) map[string]any {
	t.Helper()
	// Strict object parsing refuses duplicate/trailing envelopes, and the CLI
	// must add exactly one terminal newline instead of a second stdout record.
	envelope, err := canonical.Object(raw)
	if err != nil {
		t.Fatalf("stdout is not one strict JSON object: %v", err)
	}
	payload := "error"
	if success {
		payload = "result"
	}
	if len(envelope) != 4 || envelope["protocol"] != operations.Protocol || envelope["operation"] != operation || envelope["ok"] != success || model.M(envelope[payload]) == nil || !bytes.HasSuffix(raw, []byte{'\n'}) || bytes.Count(raw, []byte{'\n'}) != 1 {
		t.Fatalf("CLI stdout envelope is not closed: %v", envelope)
	}
	if !success {
		problem := model.M(envelope["error"])
		if model.S(problem["code"]) == "" || model.S(problem["message"]) == "" {
			t.Fatal("structured refusal lost code/message")
		}
		for key, value := range problem {
			if key != "code" && key != "message" && key != "symbol" && key != "field" && key != "operation_id" {
				t.Fatalf("unclosed error field %q", key)
			}
			if _, ok := value.(string); !ok {
				t.Fatalf("nontext error field %q", key)
			}
		}
	}
	return envelope
}

func n37Tree(t *testing.T, root string) map[string]string {
	t.Helper()
	result := map[string]string{}
	err := filepath.WalkDir(root, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, name)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		rel = filepath.ToSlash(rel)
		if entry.IsDir() {
			result[rel] = "directory"
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			t.Fatalf("owned fixture has nonregular entry %s", rel)
		}
		raw, err := os.ReadFile(name)
		if err != nil {
			return err
		}
		result[rel] = canonical.BytesHash(raw)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func n37CommittedCreate(t *testing.T, root string, request map[string]any) map[string]string {
	t.Helper()
	files, err := os.ReadDir(filepath.Join(root, ".codearbiter", ".artifacts", "transactions"))
	if err != nil {
		t.Fatal(err)
	}
	operationID := model.S(request["operation_id"])
	if len(files) != 1 || files[0].Name() != operationID+".json" {
		t.Fatalf("semantic request did not create exactly one selected journal: %v", files)
	}
	raw, err := os.ReadFile(filepath.Join(root, ".codearbiter", ".artifacts", "transactions", operationID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	journal, err := canonical.Object(raw)
	if err != nil {
		t.Fatal(err)
	}
	expectedRequest, err := canonical.Hash(map[string]any{"operation": "create", "request": request})
	if err != nil {
		t.Fatal(err)
	}
	if journal["state"] != "committed" || journal["operation_id"] != operationID || journal["request_sha256"] != expectedRequest || len(model.A(journal["entries"])) != 1 {
		t.Fatalf("commit journal does not bind the actual CLI request: %v", journal)
	}
	owner, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := repository.Scan(owner)
	if err != nil {
		owner.Close()
		t.Fatal(err)
	}
	document, err := catalog.Resolve("SPEC-EXAMPLE")
	owner.Close()
	if err != nil {
		t.Fatal(err)
	}
	if len(catalog.Order) != 1 || document.Doc.ID() != "SPEC-EXAMPLE" || document.Doc.Revision() != 1 {
		t.Fatal("one semantic create did not preserve its original artifact identity/revision")
	}
	return n37Tree(t, root)
}

func TestN37CLIValidDecodeOnceAndCommittedOutputFailure(t *testing.T) {
	t.Run("valid-create-and-exact-replay", func(t *testing.T) {
		root := testutil.Root(t)
		request, raw := n37CreateRequest(t)
		argv := []string{"create", "--root", root, "--request", "-"}
		var stdout, stderr bytes.Buffer
		if exit := run(argv, bytes.NewReader(raw), &stdout, &stderr); exit != 0 || stderr.Len() != 0 {
			t.Fatalf("valid CLI request failed: exit=%d stderr=%q", exit, stderr.String())
		}
		envelope := n37Envelope(t, stdout.Bytes(), "create", true)
		transaction := model.M(model.M(envelope["result"])["transaction"])
		if transaction["operation_id"] != request["operation_id"] || transaction["state"] != "committed" || transaction["replay"] != false {
			t.Fatalf("first call was not one original committed mutation: %v", transaction)
		}
		beforeReplay := n37CommittedCreate(t, root, request)
		stdout.Reset()
		stderr.Reset()
		if exit := run(argv, bytes.NewReader(raw), &stdout, &stderr); exit != 0 || stderr.Len() != 0 {
			t.Fatalf("exact retry failed: exit=%d stderr=%q", exit, stderr.String())
		}
		replay := model.M(model.M(n37Envelope(t, stdout.Bytes(), "create", true)["result"])["transaction"])
		if replay["operation_id"] != request["operation_id"] || replay["state"] != "committed" || replay["replay"] != true {
			t.Fatalf("exact retry did not return original committed outcome: %v", replay)
		}
		if !reflect.DeepEqual(n37CommittedCreate(t, root, request), beforeReplay) {
			t.Fatal("CLI retry repeated mutation or rewrote original committed bytes")
		}
	})
	_, valid := n37CreateRequest(t)
	unknownKey := append(append([]byte(nil), valid[:len(valid)-1]...), []byte(`,"unexpected":true}`)...)
	wrongProtocol := bytes.Replace(valid, []byte(operations.Protocol), []byte("unsupported"), 1)
	for _, tc := range []struct {
		name, operation, code string
		raw                   []byte
	}{
		{"malformed-json", "create", "INVALID_JSON", []byte("{")},
		{"duplicate-key", "create", "DUPLICATE_KEY", []byte(`{"protocol":"one","protocol":"two"}`)},
		{"trailing-json", "create", "TRAILING_JSON", append(append([]byte(nil), valid...), []byte(" {}")...)},
		{"non-object", "create", "INVALID_REQUEST", []byte("[]")},
		{"oversized-json", "create", "FILE_TOO_LARGE", bytes.Repeat([]byte{' '}, canonical.MaxBytes+1)},
		{"unknown-key", "create", "INVALID_MODEL", unknownKey},
		{"wrong-protocol", "create", "INVALID_MODEL", wrongProtocol},
		{"unknown-operation", "not-an-operation", "UNKNOWN_OPERATION", []byte(`{"protocol":"` + operations.Protocol + `"}`)},
	} {
		t.Run("refuse-"+tc.name, func(t *testing.T) {
			root := testutil.Root(t)
			before := n37Tree(t, root)
			var stdout, stderr bytes.Buffer
			exit := run([]string{tc.operation, "--root", root, "--request", "-"}, bytes.NewReader(tc.raw), &stdout, &stderr)
			envelope := n37Envelope(t, stdout.Bytes(), tc.operation, false)
			if exit != 2 || model.M(envelope["error"])["code"] != tc.code || !bytes.Contains(stderr.Bytes(), []byte(tc.code)) {
				t.Fatalf("decode/operation refusal lost structured error and exit: exit=%d envelope=%v", exit, envelope)
			}
			if !reflect.DeepEqual(n37Tree(t, root), before) {
				t.Fatal("refused CLI input reached repository mutation")
			}
		})
	}
	t.Run("committed-before-output-failure", func(t *testing.T) {
		root := testutil.Root(t)
		request, raw := n37CreateRequest(t)
		argv := []string{"create", "--root", root, "--request", "-"}
		writer := &n37FailedOutput{}
		var stderr bytes.Buffer
		if exit := run(argv, bytes.NewReader(raw), writer, &stderr); exit != 5 || writer.calls != 1 || stderr.Len() != 0 {
			t.Fatalf("write failure was not explicit: exit=%d attempts=%d stderr=%q", exit, writer.calls, stderr.String())
		}
		n37Envelope(t, writer.offered, "create", true)
		committed := n37CommittedCreate(t, root, request)
		var stdout bytes.Buffer
		if exit := run(argv, bytes.NewReader(raw), &stdout, &stderr); exit != 0 || stderr.Len() != 0 {
			t.Fatalf("same-ID recovery after failed output did not succeed: exit=%d stderr=%q", exit, stderr.String())
		}
		transaction := model.M(model.M(n37Envelope(t, stdout.Bytes(), "create", true)["result"])["transaction"])
		if transaction["operation_id"] != request["operation_id"] || transaction["replay"] != true || transaction["state"] != "committed" {
			t.Fatalf("failed delivery lost original outcome: %v", transaction)
		}
		if !reflect.DeepEqual(n37CommittedCreate(t, root, request), committed) {
			t.Fatal("lost stdout response caused a second semantic write")
		}
	})
}
