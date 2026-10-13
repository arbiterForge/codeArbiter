package contextdocument

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// validateCodeMapTargets checks only the bounded, proposed map entries. It
// never rewrites an existing human map or performs a repository-wide scan.
func validateCodeMapTargets(f *store.FS, preview Preview) error {
	if preview.DocumentID != "code-map" {
		return nil
	}
	if len(preview.Bytes) > 20*1024 || countMapEntries(preview.ProposedEntries) > 50 {
		return fault.New("INVALID_CONTEXT_MUTATION", "code map exceeds 20 KiB or 50 entries")
	}
	for _, entry := range preview.ProposedEntries {
		if entry.Kind != "map_entry" {
			continue
		}
		for _, target := range entry.MapEntry.Paths {
			if _, err := f.Stat(target); err != nil {
				return fault.New("SOURCE_EVIDENCE_CONFLICT", "code map target is missing or unsafe")
			}
		}
	}
	return nil
}
