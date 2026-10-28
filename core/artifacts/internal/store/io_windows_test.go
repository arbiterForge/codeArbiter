//go:build windows

package store

import (
	"os"
	"strings"
	"syscall"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

func TestNativeWindowsOperationalFaultsAreBounded(t *testing.T) {
	for _, tc := range []struct {
		name string
		code syscall.Errno
		kind string
	}{
		{"access denied", syscall.ERROR_ACCESS_DENIED, "EACCES"},
		{"disk full", syscall.Errno(112), "ERROR_DISK_FULL"},
		{"handle disk full", syscall.Errno(39), "ERROR_HANDLE_DISK_FULL"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cause := &os.PathError{Op: "write", Path: "private/credential=do-not-echo", Err: tc.code}
			if !isOperationalIO(cause) {
				t.Fatal("native Windows fault was not recognized as operational I/O")
			}
			got := ioFault("write artifact", "draft.html", cause)
			pub := fault.Public(got)
			if pub.Code != "IO_ERROR" || pub.Field != "draft.html" || fault.Exit(got) != 5 ||
				!strings.Contains(pub.Message, tc.kind) || strings.Contains(pub.Message, "credential=do-not-echo") {
				t.Fatalf("native Windows fault was not bounded: %+v, exit %d", pub, fault.Exit(got))
			}
		})
	}
}
