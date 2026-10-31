package operations

import (
	"os"
	"path/filepath"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// The legacy Python writer locks the first byte of this sidecar. A native
// cutover must coordinate with that exact file before reading either board.
func openLegacyBoardLock(root string) (*os.File, error) {
	path := filepath.Join(root, ".codearbiter", "open-tasks.md.lock")
	before, err := os.Lstat(path)
	if err == nil {
		if !before.Mode().IsRegular() {
			return nil, fault.New("LEGACY_LOCK_FAILED", "legacy board lock is not a regular file")
		}
	} else if !os.IsNotExist(err) {
		return nil, fault.New("LEGACY_LOCK_FAILED", "cannot inspect legacy board lock")
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, fault.New("LEGACY_LOCK_FAILED", "cannot open legacy board lock")
	}
	info, err := file.Stat()
	pathInfo, pathErr := os.Lstat(path)
	if err != nil || pathErr != nil || !info.Mode().IsRegular() || !pathInfo.Mode().IsRegular() ||
		!os.SameFile(pathInfo, info) || (before != nil && !os.SameFile(before, info)) || !singleLink(file) {
		file.Close()
		return nil, fault.New("LEGACY_LOCK_FAILED", "legacy board lock is linked or changed")
	}
	if info.Size() == 0 {
		if _, err := file.WriteAt([]byte{0}, 0); err != nil {
			file.Close()
			return nil, fault.New("LEGACY_LOCK_FAILED", "cannot seed legacy board lock")
		}
		if err := file.Sync(); err != nil {
			file.Close()
			return nil, fault.New("LEGACY_LOCK_FAILED", "cannot sync legacy board lock")
		}
	}
	return file, nil
}
