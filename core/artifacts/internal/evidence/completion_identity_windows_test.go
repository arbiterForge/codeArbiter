//go:build windows

package evidence

import (
	"fmt"
	"math/big"
	"reflect"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func completionLegacyFixture(t *testing.T, id string) string {
	t.Helper()
	parts := strings.Split(id, ":")
	if len(parts) != 2 {
		t.Fatal("malformed Python identity fixture")
	}
	dev, devOK := new(big.Int).SetString(parts[0], 10)
	ino, inoOK := new(big.Int).SetString(parts[1], 10)
	if !devOK || !inoOK {
		t.Fatal("malformed Python identity integers")
	}
	// CPython <=3.11 uses BY_HANDLE_FILE_INFORMATION: DWORD volume serial,
	// followed by its two DWORD file-index halves, rather than FILE_ID_INFO.
	return fmt.Sprintf("%d:%d", uint32(dev.Uint64()), ino.Uint64())
}

func TestCompletionWorkspaceLegacyWindowsIdentity(t *testing.T) {
	f := completionFixture(t)
	bindings, want := completionPython(t, f.Root)
	for _, value := range bindings {
		b := model.M(value)
		for _, field := range []string{"cwd_filesystem_id", "workspace_filesystem_id", "git_common_filesystem_id"} {
			b[field] = completionLegacyFixture(t, model.S(b[field]))
		}
		for _, value := range model.A(b["launch_files"]) {
			item := model.M(value)
			item["filesystem_id"] = completionLegacyFixture(t, model.S(item["filesystem_id"]))
		}
	}
	for _, value := range want {
		snapshot := model.M(value)
		for _, field := range []string{"filesystem_id", "git_common_filesystem_id"} {
			snapshot[field] = completionLegacyFixture(t, model.S(snapshot[field]))
		}
	}
	got, err := CompletionWorkspaces(f, bindings, false)
	if err != nil {
		t.Fatalf("supported older Python identity cannot be validated: %v", err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("legacy identity was not retained exactly\ngot %v\nwant %v", got, want)
	}
	model.M(bindings[0])["workspace_filesystem_id"] = "1:1"
	if _, err := CompletionWorkspaces(f, bindings, false); err == nil {
		t.Fatal("unrelated identity accepted as legacy Windows identity")
	}
}
