package contextdocument

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// The seven expected digests came from the real T-008
// _contextsnapshotlib.membership_snapshot on the identical file fixture,
// retained in brownfield-t015-membership-oracle.py and the author handoff.
func assertMembershipParity(t *testing.T) {
	t.Helper()
	root := t.TempDir()
	for _, dir := range []string{".git", "nested/.git", "submodule", "Z", "a"} {
		if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(dir)), 0755); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "submodule", ".git"), []byte("gitdir: elsewhere"), 0644); err != nil {
		t.Fatal(err)
	}
	for _, relative := range []string{"package.json", "AGENTS.md", ".editorconfig", "tests/test_unit.py", "infra/Dockerfile", "security/SECURITY.md", "migrations/schema.sql", "vendor/package.json", "generated/AGENTS.md", "nested/package.json", "submodule/package.json", "Zoo", "alpha"} {
		path := filepath.Join(root, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte("fixture\n"), 0644); err != nil {
			t.Fatal(err)
		}
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	want := map[string]string{
		"manifests":      "19f97e9f165b271cc4369c10bfe66692e76e6b3323392bd53782a037dc16e3d2",
		"instructions":   "3ce3b662c14ab78b08405da13b7e4e9b34c7e2e70525c4f28de81b80ce10f768",
		"configuration":  "cf1f96c5ebcc2b8fe52f9637072598e2ec3b45b6a5eee9c90644966c52696b57",
		"tests":          "c1d57aa10b265cc5b4876c88fd2c883321dbb9df17a1b9f810ce0694a9e807d6",
		"infrastructure": "eded6d5a48528c08a0fc317cfc168e78bdd55c127aa7dea3d5dbaefea58be9a6",
		"security":       "df173d9788bc451bc584b68b0dc82b3f9b2fbd03147f6e52fd57889670e782b8",
		"data":           "0dc207d91fa0ef9e55d044dab722ba2b689e02f35bca1a95aef62ebb87ef7f73",
	}
	for predicate, expected := range want {
		got, err := MembershipDigest(f, predicate, []string{"."})
		if err != nil || got != expected {
			t.Errorf("Python membership parity %s: got %s want %s error %v", predicate, got, expected, err)
		}
	}
	if got, err := MembershipDigest(f, "manifests", []string{"a", "Z"}); err != nil || got != "992a8bcac4bb677d6c63ca065f130f2a58276020cd8537b14b9d2b032591aba9" {
		t.Fatalf("Python ordinal scope parity: %s %v", got, err)
	}
	before, err := MembershipDigest(f, "manifests", []string{"."})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "pyproject.toml"), []byte("[project]\n"), 0644); err != nil {
		t.Fatal(err)
	}
	after, err := MembershipDigest(f, "manifests", []string{"."})
	if err != nil || before == after {
		t.Fatalf("new manifest did not change membership: %s %s %v", before, after, err)
	}
	for _, tc := range []struct {
		predicate string
		scopes    []string
	}{
		{"source", []string{"."}}, {"manifests", []string{"../outside"}},
		{"manifests", []string{"src-é"}}, {"manifests", []string{".", "vendor"}},
	} {
		if _, err := MembershipDigest(f, tc.predicate, tc.scopes); err == nil {
			t.Errorf("unsupported membership selector accepted: %s %+v", tc.predicate, tc.scopes)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "AGÉNTS.md"), []byte("x"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := MembershipDigest(f, "instructions", []string{"."}); fault.Code(err) != "SOURCE_EVIDENCE_UNSUPPORTED" {
		t.Fatalf("Unicode casefold was approximated: %v", err)
	}
	missingRoot := t.TempDir()
	missing, err := store.Open(missingRoot)
	if err != nil {
		t.Fatal(err)
	}
	defer missing.Close()
	if _, err := MembershipDigest(missing, "manifests", []string{"vendor"}); fault.Code(err) != "SOURCE_EVIDENCE_UNKNOWN" {
		t.Fatalf("missing vendor scope gained a digest: %v", err)
	}
	linkedTarget := t.TempDir()
	if err := os.Symlink(linkedTarget, filepath.Join(missingRoot, "vendor")); err == nil {
		if _, err := MembershipDigest(missing, "manifests", []string{"vendor"}); fault.Code(err) != "SOURCE_EVIDENCE_UNKNOWN" {
			t.Fatalf("linked vendor scope gained a digest: %v", err)
		}
	}
}
