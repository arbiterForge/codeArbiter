//go:build linux || darwin

package evidence

import (
	"fmt"
	"os"
	"syscall"
)

func completionNativeIdentity(path string) (string, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return "", err
	}
	st := info.Sys().(*syscall.Stat_t)
	return fmt.Sprintf("%d:%d", uint64(st.Dev), st.Ino), nil
}

func completionReparse(info os.FileInfo) bool { return false }

func completionLegacyIdentity(path string) (string, error) { return completionNativeIdentity(path) }
