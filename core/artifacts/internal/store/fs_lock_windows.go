//go:build windows

package store

import (
	"os"
	"runtime"
	"syscall"
	"time"
	"unsafe"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

const (
	lockfileFailImmediately = 0x00000001
	lockfileExclusiveLock   = 0x00000002
	errorLockViolation      = syscall.Errno(33)
	ntLockGenericRead       = 0x120089 // read/list, read attributes/EA, READ_CONTROL and SYNCHRONIZE
	ntLockCaseInsensitive   = 0x40
	ntLockDontReparse       = 0x1000
	ntLockOpen              = 1
	ntLockDirectoryFile     = 1
	ntLockSynchronousIO     = 0x20
	ntLockOpenReparsePoint  = 0x200000
)

var (
	kernel32         = syscall.NewLazyDLL("kernel32.dll")
	procLockFileEx   = kernel32.NewProc("LockFileEx")
	procUnlockFileEx = kernel32.NewProc("UnlockFileEx")
	procReOpenFile   = kernel32.NewProc("ReOpenFile")
	procNtCreateFile = syscall.NewLazyDLL("ntdll.dll").NewProc("NtCreateFile")
)

// These closed native layouts match Windows UNICODE_STRING, OBJECT_ATTRIBUTES
// and IO_STATUS_BLOCK on both supported pointer widths. Directory pins use only
// the already-anchored handle and the empty self name, never an absolute path.
type lockUnicodeString struct {
	Length, MaximumLength uint16
	Buffer                *uint16
}
type lockObjectAttributes struct {
	Length                                       uint32
	RootDirectory                                uintptr
	ObjectName                                   *lockUnicodeString
	Attributes                                   uint32
	SecurityDescriptor, SecurityQualityOfService uintptr
}
type lockIOStatus struct{ Status, Information uintptr }

func (f *FS) nativeLock(exclusive bool, timeout time.Duration) (func(), error) {
	return f.windowsLock(exclusive, timeout, false)
}

// ObservationLock never initializes metadata or requests write access. Mutex
// sharing remains independent of access rights: index still locks exclusively.
func (f *FS) ObservationLock(exclusive bool, timeout time.Duration) (func(), error) {
	return f.windowsLock(exclusive, timeout, true)
}

// ObservationStateMissing reports that the untracked lock file is absent, as on
// every fresh clone or worktree. The engine then takes the writer Lock, which
// initializes the store as reads did before observation locks existed (#994).
// Any present or unsafe state reports false, so ObservationLock still refuses it.
func (f *FS) ObservationStateMissing() bool {
	_, err := f.root.Lstat(native(meta + "/store.lock"))
	return os.IsNotExist(err)
}

// pinLockObject reopens an already-contained handle without FILE_SHARE_DELETE.
// os.Root opens share deletion on Windows; those original handles alone cannot
// prevent an active mutex or an ancestor from being replaced under another name.
func pinLockObject(file *os.File, directory bool) (*os.File, error) {
	info, err := file.Stat()
	if err != nil || !ordinaryLockObject(info, directory) {
		return nil, fault.New("UNSAFE_PATH", "repository lock requires ordinary objects")
	}
	if directory {
		// NT uses an empty name for the RootDirectory itself (the same spelling
		// used by Go's Windows Openat for os.Root.Open(".")).
		name := [...]uint16{0}
		unicode := lockUnicodeString{0, 2, &name[0]}
		attributes := lockObjectAttributes{Length: uint32(unsafe.Sizeof(lockObjectAttributes{})), RootDirectory: file.Fd(), ObjectName: &unicode, Attributes: ntLockCaseInsensitive | ntLockDontReparse}
		var handle uintptr
		var status lockIOStatus
		// FILE_GENERIC_READ, FILE_OPEN, DIRECTORY_FILE, SYNCHRONOUS_IO_NONALERT
		// and OPEN_REPARSE_POINT; reject reparsing and share only read/write.
		result, _, _ := procNtCreateFile.Call(uintptr(unsafe.Pointer(&handle)), ntLockGenericRead, uintptr(unsafe.Pointer(&attributes)), uintptr(unsafe.Pointer(&status)), 0, 0, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE, ntLockOpen, ntLockDirectoryFile|ntLockSynchronousIO|ntLockOpenReparsePoint, 0, 0)
		runtime.KeepAlive(file)
		runtime.KeepAlive(&attributes)
		runtime.KeepAlive(&unicode)
		runtime.KeepAlive(&name)
		runtime.KeepAlive(&status)
		if int32(result) != 0 || handle == 0 || handle == ^uintptr(0) {
			if handle != 0 && handle != ^uintptr(0) {
				_ = syscall.CloseHandle(syscall.Handle(handle))
			}
			return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
		}
		return ownLockHandle(handle)
	}
	handle, _, _ := procReOpenFile.Call(file.Fd(), syscall.GENERIC_READ, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE, 0)
	runtime.KeepAlive(file)
	if handle == 0 || handle == ^uintptr(0) {
		return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
	}
	return ownLockHandle(handle)
}

func ownLockHandle(handle uintptr) (*os.File, error) {
	file := os.NewFile(handle, "repository lock anchor")
	if file == nil {
		_ = syscall.CloseHandle(syscall.Handle(handle))
		return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
	}
	return file, nil
}

func ordinaryLockObject(info os.FileInfo, directory bool) bool {
	if info == nil {
		return false
	}
	attributes, ok := info.Sys().(*syscall.Win32FileAttributeData)
	if !ok || attributes.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
		return false
	}
	if directory {
		return info.IsDir() && info.Mode()&os.ModeSymlink == 0
	}
	return info.Mode().IsRegular()
}

func checkLockObject(file *os.File, root *os.Root, name string, directory bool) error {
	named, e := root.Lstat(name)
	if e != nil {
		return fault.New("CONCURRENT_CHANGE", "repository lock identity changed")
	}
	opened, e := file.Stat()
	if e != nil || !ordinaryLockObject(named, directory) || !ordinaryLockObject(opened, directory) {
		return fault.New("UNSAFE_PATH", "repository lock requires ordinary objects")
	}
	if !os.SameFile(opened, named) {
		return fault.New("CONCURRENT_CHANGE", "repository lock identity changed")
	}
	return nil
}

func (f *FS) windowsLock(exclusive bool, timeout time.Duration, observation bool) (func(), error) {
	for _, procedure := range []*syscall.LazyProc{procLockFileEx, procUnlockFileEx, procReOpenFile, procNtCreateFile} {
		if e := procedure.Find(); e != nil {
			return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
		}
	}
	var files []*os.File
	var dirs []*Dir
	closeAll := func() {
		for i := len(files) - 1; i >= 0; i-- {
			_ = files[i].Close()
		}
		for i := len(dirs) - 1; i >= 0; i-- {
			_ = dirs[i].Close()
		}
	}
	success := false
	defer func() {
		if !success {
			closeAll()
		}
	}()
	rootFile, e := f.root.Open(".")
	if e != nil {
		return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
	}
	files = append(files, rootFile)
	if e = f.step("lock-after-root-open"); e != nil {
		return nil, e
	}
	rootPin, e := pinLockObject(rootFile, true)
	if e != nil {
		return nil, e
	}
	files = append(files, rootPin)
	checkRoot := func() error {
		named, err := os.Lstat(f.Root)
		opened, statErr := rootPin.Stat()
		if err != nil || statErr != nil {
			return fault.New("CONCURRENT_CHANGE", "repository lock identity changed")
		}
		if !ordinaryLockObject(named, true) || !ordinaryLockObject(opened, true) {
			return fault.New("UNSAFE_PATH", "repository lock requires ordinary objects")
		}
		if !os.SameFile(opened, named) {
			return fault.New("CONCURRENT_CHANGE", "repository lock identity changed")
		}
		return nil
	}
	if e = checkRoot(); e != nil {
		return nil, e
	}
	var pins []*os.File
	for _, rel := range []string{".codearbiter", meta} {
		if named, err := f.root.Lstat(native(rel)); err == nil && !ordinaryLockObject(named, true) {
			return nil, fault.New("UNSAFE_PATH", "repository lock requires ordinary objects")
		}
		if !observation {
			if e = f.check(rel, true); e != nil {
				return nil, e
			}
			if e = f.root.MkdirAll(native(rel), 0755); e != nil {
				return nil, e
			}
		}
		dir, err := f.OpenDir(rel)
		if err != nil {
			if os.IsNotExist(err) || observation && fault.Code(err) == "INTERNAL_ERROR" {
				return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
			}
			return nil, err
		}
		dirs = append(dirs, dir)
		opened, err := dir.root.Open(".")
		if err != nil {
			return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
		}
		files = append(files, opened)
		if e = f.step("lock-after-directory-open:" + rel); e != nil {
			return nil, e
		}
		pin, err := pinLockObject(opened, true)
		if err != nil {
			return nil, err
		}
		files = append(files, pin)
		pins = append(pins, pin)
		if e = checkLockObject(pin, f.root, native(rel), true); e != nil {
			return nil, e
		}
	}
	metadata := dirs[len(dirs)-1].root
	if named, err := metadata.Lstat("store.lock"); err == nil {
		if !ordinaryLockObject(named, false) {
			return nil, fault.New("UNSAFE_PATH", "repository lock requires ordinary objects")
		}
	} else if observation || !os.IsNotExist(err) {
		return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
	}
	openFlags := os.O_RDONLY
	if !observation {
		openFlags = os.O_RDWR | os.O_CREATE
	}
	file, e := metadata.OpenFile("store.lock", openFlags, 0600)
	if e != nil {
		return nil, fault.New("LOCK_FAILED", "existing repository lock is unavailable")
	}
	files = append(files, file)
	if e = f.step("lock-after-file-open"); e != nil {
		return nil, e
	}
	lockPin, e := pinLockObject(file, false)
	if e != nil {
		return nil, e
	}
	files = append(files, lockPin)
	checkAll := func() error {
		if err := checkRoot(); err != nil {
			return err
		}
		for i, rel := range []string{".codearbiter", meta} {
			if err := checkLockObject(pins[i], f.root, native(rel), true); err != nil {
				return err
			}
		}
		return checkLockObject(lockPin, metadata, "store.lock", false)
	}
	if e = checkAll(); e != nil {
		return nil, e
	}
	if e = f.step("lock-before-acquire"); e != nil {
		return nil, e
	}
	if e = checkAll(); e != nil {
		return nil, e
	}
	flags := uint32(lockfileFailImmediately)
	if exclusive {
		flags |= lockfileExclusiveLock
	}
	var overlap syscall.Overlapped
	deadline := time.Now().Add(timeout)
	for {
		r, _, callErr := procLockFileEx.Call(file.Fd(), uintptr(flags), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
		runtime.KeepAlive(file)
		if r != 0 {
			if e = checkAll(); e != nil {
				_, _, _ = procUnlockFileEx.Call(file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
				return nil, e
			}
			success = true
			return func() {
				_, _, _ = procUnlockFileEx.Call(file.Fd(), 0, 1, 0, uintptr(unsafe.Pointer(&overlap)))
				closeAll()
			}, nil
		}
		if callErr != errorLockViolation {
			return nil, fault.New("LOCK_FAILED", "cannot lock repository")
		}
		if time.Now().After(deadline) {
			return nil, fault.New("LOCK_TIMEOUT", "repository is busy; retry with a fresh read")
		}
		time.Sleep(10 * time.Millisecond)
	}
}
