//go:build windows

package testutil

import (
	"crypto/sha256"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"testing"
	"unsafe"
)

var (
	fixtureAdvapi          = syscall.NewLazyDLL("advapi32.dll")
	fixtureGetSecurity     = fixtureAdvapi.NewProc("GetFileSecurityW")
	fixtureSetSecurity     = fixtureAdvapi.NewProc("SetFileSecurityW")
	fixtureConvertSecurity = fixtureAdvapi.NewProc("ConvertStringSecurityDescriptorToSecurityDescriptorW")
	fixtureSecurityControl = fixtureAdvapi.NewProc("GetSecurityDescriptorControl")
)

// ReadOnlyFixture creates and owns a disposable root, initializes it with the
// ordinary writer, then denies data writes, creates and deletes to this process's
// user. WRITE_DAC remains available to restore the exact original DACLs. No
// caller-supplied root can be passed to this permission-changing helper.
func ReadOnlyFixture(t testing.TB, initialize func(string)) string {
	t.Helper()
	root := Root(t)
	initialize(root)
	token, err := syscall.OpenCurrentProcessToken()
	if err != nil {
		t.Fatal("fixture process identity:", err)
	}
	defer token.Close()
	user, err := token.GetTokenUser()
	if err != nil {
		t.Fatal("fixture user:", err)
	}
	sid, err := user.User.Sid.String()
	if err != nil {
		t.Fatal("fixture SID:", err)
	}
	sddl, err := syscall.UTF16PtrFromString("D:P(D;;0x00010156;;;" + sid + ")(A;;FA;;;" + sid + ")")
	if err != nil {
		t.Fatal(err)
	}
	var deny uintptr
	r, _, callErr := fixtureConvertSecurity.Call(uintptr(unsafe.Pointer(sddl)), 1, uintptr(unsafe.Pointer(&deny)), 0)
	if r == 0 {
		t.Fatal("fixture DACL conversion:", callErr)
	}
	defer syscall.LocalFree(syscall.Handle(deny))
	type savedACL struct {
		path    string
		info    fs.FileInfo
		bytes   []byte
		control uint16
	}
	var originals []savedACL
	err = filepath.WalkDir(root, func(p string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(root, p)
		if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			return fmt.Errorf("fixture path escaped")
		}
		info, err := os.Lstat(p)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 || (!info.IsDir() && !info.Mode().IsRegular()) {
			return fmt.Errorf("fixture requires ordinary entries")
		}
		name, err := syscall.UTF16PtrFromString(p)
		if err != nil {
			return err
		}
		var size uint32
		fixtureGetSecurity.Call(uintptr(unsafe.Pointer(name)), 4, 0, 0, uintptr(unsafe.Pointer(&size)))
		if size == 0 || size > 65536 {
			return fmt.Errorf("fixture DACL size invalid")
		}
		buf := make([]byte, size)
		r, _, callErr := fixtureGetSecurity.Call(uintptr(unsafe.Pointer(name)), 4, uintptr(unsafe.Pointer(&buf[0])), uintptr(size), uintptr(unsafe.Pointer(&size)))
		if r == 0 {
			return fmt.Errorf("fixture save DACL: %w", callErr)
		}
		var control uint16
		var revision uint32
		r, _, callErr = fixtureSecurityControl.Call(uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&control)), uintptr(unsafe.Pointer(&revision)))
		if r == 0 {
			return fmt.Errorf("fixture DACL control: %w", callErr)
		}
		originals = append(originals, savedACL{p, info, buf, control})
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	// Register restoration before applying any DACL, including a partial failure.
	t.Cleanup(func() {
		for i := len(originals) - 1; i >= 0; i-- {
			a := originals[i]
			info, err := os.Lstat(a.path)
			if err != nil || !os.SameFile(info, a.info) || info.Mode()&os.ModeSymlink != 0 {
				t.Errorf("fixture DACL restore identity changed")
				continue
			}
			name, err := syscall.UTF16PtrFromString(a.path)
			if err != nil {
				t.Error(err)
				continue
			}
			securityInfo := uintptr(4 | 0x20000000)
			if a.control&0x1000 != 0 {
				securityInfo = 4 | 0x80000000
			}
			r, _, callErr := fixtureSetSecurity.Call(uintptr(unsafe.Pointer(name)), securityInfo, uintptr(unsafe.Pointer(&a.bytes[0])))
			if r == 0 {
				t.Errorf("fixture DACL restoration: %v", callErr)
			}
		}
	})
	for i := len(originals) - 1; i >= 0; i-- {
		name, err := syscall.UTF16PtrFromString(originals[i].path)
		if err != nil {
			t.Fatal(err)
		}
		r, _, callErr := fixtureSetSecurity.Call(uintptr(unsafe.Pointer(name)), 4|0x80000000, deny)
		if r == 0 {
			t.Fatal("fixture set DACL:", callErr)
		}
	}
	return root
}

// Tree records every ordinary fixture name, content and last-write metadata.
func Tree(t testing.TB, root string) map[string]string {
	t.Helper()
	out := map[string]string{}
	err := filepath.WalkDir(root, func(p string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		info, err := os.Lstat(p)
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		value := fmt.Sprintf("%s %d %d", info.Mode(), info.Size(), info.ModTime().UnixNano())
		attributes, ok := info.Sys().(*syscall.Win32FileAttributeData)
		if ok {
			value += fmt.Sprintf(" attributes=%x", attributes.FileAttributes)
		}
		if info.Mode().IsRegular() && (!ok || attributes.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT == 0) {
			b, err := os.ReadFile(p)
			if err != nil {
				return err
			}
			value += fmt.Sprintf(" %x", sha256.Sum256(b))
		}
		out[filepath.ToSlash(rel)] = value
		if ok && attributes.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0 && info.IsDir() {
			return filepath.SkipDir
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func AssertTree(t testing.TB, root string, want map[string]string) {
	t.Helper()
	if got := Tree(t, root); !reflect.DeepEqual(got, want) {
		t.Fatalf("observation changed fixture names, bytes or last-write metadata: got %v want %v", got, want)
	}
}
