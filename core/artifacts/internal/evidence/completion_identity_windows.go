//go:build windows

package evidence

import (
	"encoding/binary"
	"fmt"
	"math/big"
	"os"
	"syscall"
	"unsafe"
)

var completionFileInformation = syscall.NewLazyDLL("kernel32.dll").NewProc("GetFileInformationByHandleEx")

func completionNativeIdentity(path string) (string, error) {
	name, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return "", err
	}
	handle, err := syscall.CreateFile(name, 0, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if err != nil {
		return "", err
	}
	defer syscall.CloseHandle(handle)
	// CPython 3.12+ uses the 64-bit volume serial and 128-bit FileIdInfo
	// identifier, both native little-endian. Do not truncate to the older
	// BY_HANDLE_FILE_INFORMATION representation.
	var data [24]byte
	ok, _, callErr := completionFileInformation.Call(uintptr(handle), 18, uintptr(unsafe.Pointer(&data[0])), uintptr(len(data)))
	if ok == 0 {
		return "", callErr
	}
	var inode [16]byte
	for i := range inode {
		inode[i] = data[23-i]
	}
	return fmt.Sprintf("%d:%s", binary.LittleEndian.Uint64(data[:8]), new(big.Int).SetBytes(inode[:]).String()), nil
}

func completionReparse(info os.FileInfo) bool {
	attributes, ok := info.Sys().(*syscall.Win32FileAttributeData)
	return ok && attributes.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0
}

func completionLegacyIdentity(path string) (string, error) {
	name, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return "", err
	}
	handle, err := syscall.CreateFile(name, 0, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if err != nil {
		return "", err
	}
	defer syscall.CloseHandle(handle)
	var info syscall.ByHandleFileInformation
	if err := syscall.GetFileInformationByHandle(handle, &info); err != nil {
		return "", err
	}
	return fmt.Sprintf("%d:%d", info.VolumeSerialNumber, uint64(info.FileIndexHigh)<<32|uint64(info.FileIndexLow)), nil
}
