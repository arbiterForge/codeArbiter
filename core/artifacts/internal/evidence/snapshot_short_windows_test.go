package evidence

import (
	"syscall"
	"testing"
)

// shortNameOf returns the volume's 8.3 short form of an existing path's final
// component, or "" when the volume generates none.
func shortNameOf(t *testing.T, full string) string {
	t.Helper()
	long, err := syscall.UTF16PtrFromString(full)
	if err != nil {
		t.Fatal(err)
	}
	buf := make([]uint16, 1024)
	n, err := syscall.GetShortPathName(long, &buf[0], uint32(len(buf)))
	if err != nil || n == 0 || int(n) > len(buf) {
		return ""
	}
	out := syscall.UTF16ToString(buf[:n])
	for i := len(out) - 1; i >= 0; i-- {
		if out[i] == '\\' || out[i] == '/' {
			return out[i+1:]
		}
	}
	return out
}
