"""Single bounded local stage-file writer.

POSIX uses directory-fd-relative creation with O_NOFOLLOW. Windows uses
handle-relative NtCreateFile calls, one path component at a time. Directory
handles are held without FILE_SHARE_DELETE while writing, and each opened
component is inspected for FILE_ATTRIBUTE_REPARSE_POINT. There is deliberately
no path-based Windows write fallback: if the native handle boundary is
unavailable, the operation fails closed.
"""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path


class ImmutableStageConflict(OSError):
    """The already-existing staged file differs from the immutable intent."""


def _single_component(value: str) -> str:
    if (not isinstance(value, str) or not value or value in (".", "..")
        or "/" in value or "\\" in value or "\x00" in value):
        raise ValueError("Stage path must contain only bounded single components")
    return value


def _write_posix(workspace: Path, folders: tuple[str, ...], filename: str,
                 data: bytes, *, crash_after_write: bool) -> str:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("No trustworthy dirfd-relative staging support")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(str(workspace), flags)
    try:
        for part in folders:
            try:
                os.mkdir(part, dir_fd=directory_fd)
            except FileExistsError:
                pass
            next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            fd = os.open(filename,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
        except FileExistsError:
            with os.fdopen(os.open(
                filename, os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd), "rb") as stream:
                if stream.read(len(data) + 1) != data:
                    raise ImmutableStageConflict("Existing immutable stage differs")
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if crash_after_write:
                os._exit(79)  # Explicit fault-injection path; OS closes descriptors.
        with os.fdopen(os.open(
            filename, os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd), "rb") as stream:
            actual = stream.read(len(data) + 1)
        if actual != data:
            raise ImmutableStageConflict("Staged file readback differs")
        return hashlib.sha256(actual).hexdigest()
    finally:
        os.close(directory_fd)


# Windows native constants. NtCreateFile is called only with one component in
# ObjectName: FILE_OPEN_REPARSE_POINT protects that final component, and the
# parent is always an already-open directory handle.
_WIN_FILE_LIST_DIRECTORY = 0x00000001
_WIN_FILE_READ_DATA = 0x00000001
_WIN_FILE_WRITE_DATA = 0x00000002
_WIN_FILE_TRAVERSE = 0x00000020
_WIN_FILE_READ_ATTRIBUTES = 0x00000080
_WIN_SYNCHRONIZE = 0x00100000
_WIN_FILE_SHARE_READ = 0x00000001
_WIN_FILE_SHARE_WRITE = 0x00000002
_WIN_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_WIN_FILE_ATTRIBUTE_NORMAL = 0x00000080
_WIN_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_WIN_OPEN_EXISTING = 3
_WIN_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WIN_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WIN_FILE_OPEN = 0x00000001
_WIN_FILE_CREATE = 0x00000002
_WIN_FILE_OPEN_IF = 0x00000003
_WIN_FILE_DIRECTORY_FILE = 0x00000001
_WIN_FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
_WIN_FILE_NON_DIRECTORY_FILE = 0x00000040
_WIN_FILE_OPEN_REPARSE_POINT = 0x00200000
_WIN_OBJ_CASE_INSENSITIVE = 0x00000040
_WIN_FILE_ATTRIBUTE_TAG_INFO = 9
_WIN_STATUS_OBJECT_NAME_COLLISION = 0xC0000035
_WIN_STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
_WIN_STATUS_OBJECT_PATH_NOT_FOUND = 0xC000003A
_WIN_STATUS_NOT_A_DIRECTORY = 0xC0000103
_WIN_STATUS_FILE_IS_A_DIRECTORY = 0xC00000BA
_WIN_STATUS_SHARING_VIOLATION = 0xC0000043
_WIN_STATUS_ACCESS_DENIED = 0xC0000022

_WINDOWS_API = None


def _windows_api():
    """Load and cache the small Win32/NT API surface used by the writer."""
    global _WINDOWS_API
    if _WINDOWS_API is not None:
        return _WINDOWS_API

    import ctypes
    from ctypes import wintypes

    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", ctypes.c_void_p),
            ("SecurityQualityOfService", ctypes.c_void_p),
        ]

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [
            ("Status", wintypes.LONG),
            ("Information", ctypes.c_size_t),
        ]

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
    ]
    ntdll.NtCreateFile.restype = wintypes.LONG

    _WINDOWS_API = (
        ctypes, wintypes, kernel32, ntdll,
        UnicodeString, ObjectAttributes, IoStatusBlock, FileAttributeTagInfo,
    )
    return _WINDOWS_API


def _ntstatus_error(status: int, name: str) -> OSError:
    code = int(status) & 0xFFFFFFFF
    message = f"NtCreateFile failed for {name!r} (NTSTATUS 0x{code:08X})"
    if code == _WIN_STATUS_OBJECT_NAME_COLLISION:
        return FileExistsError(errno.EEXIST, message, name)
    if code in (_WIN_STATUS_OBJECT_NAME_NOT_FOUND, _WIN_STATUS_OBJECT_PATH_NOT_FOUND):
        return FileNotFoundError(errno.ENOENT, message, name)
    if code == _WIN_STATUS_NOT_A_DIRECTORY:
        return NotADirectoryError(errno.ENOTDIR, message, name)
    if code == _WIN_STATUS_FILE_IS_A_DIRECTORY:
        return IsADirectoryError(errno.EISDIR, message, name)
    if code in (_WIN_STATUS_SHARING_VIOLATION, _WIN_STATUS_ACCESS_DENIED):
        return PermissionError(errno.EACCES, message, name)
    return OSError(errno.EIO, message, name)


def _nt_create_file_relative(parent_handle: int, name: str, *,
                             desired_access: int, share_access: int,
                             disposition: int, create_options: int,
                             file_attributes: int = _WIN_FILE_ATTRIBUTE_NORMAL) -> int:
    """Open/create exactly one child name relative to an already-open directory.

    The one-component restriction is security-critical: FILE_OPEN_REPARSE_POINT
    applies to the final component only. Never pass a path containing a slash.
    """
    if (not isinstance(name, str) or not name or name in (".", "..")
        or any(char in name for char in ("\\", "/", ":", "\x00"))):
        raise ValueError("Windows relative open requires one ordinary path component")

    (ctypes, wintypes, _kernel32, ntdll,
     UnicodeString, ObjectAttributes, IoStatusBlock, _FileAttributeTagInfo) = _windows_api()

    encoded = name.encode("utf-16-le")
    if len(encoded) > 0xFFFC:
        raise ValueError("Windows path component exceeds UNICODE_STRING limit")
    name_buffer = ctypes.create_unicode_buffer(name)
    unicode_name = UnicodeString(
        len(encoded), len(encoded) + 2,
        ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    object_attributes = ObjectAttributes()
    object_attributes.Length = ctypes.sizeof(ObjectAttributes)
    object_attributes.RootDirectory = wintypes.HANDLE(parent_handle)
    object_attributes.ObjectName = ctypes.pointer(unicode_name)
    # Deliberately use only OBJ_CASE_INSENSITIVE. Reparse protection is
    # component-wise via FILE_OPEN_REPARSE_POINT, not OBJ_DONT_REPARSE.
    object_attributes.Attributes = _WIN_OBJ_CASE_INSENSITIVE

    handle = wintypes.HANDLE()
    io_status = IoStatusBlock()
    status = ntdll.NtCreateFile(
        ctypes.byref(handle),
        desired_access,
        ctypes.byref(object_attributes),
        ctypes.byref(io_status),
        None,
        file_attributes,
        share_access,
        disposition,
        create_options,
        None,
        0,
    )
    status_code = int(status) & 0xFFFFFFFF
    if status_code != 0:
        raise _ntstatus_error(status_code, name)
    if handle.value is None:
        raise OSError(errno.EIO, f"NtCreateFile returned a null handle for {name!r}")
    return int(handle.value)


def _windows_file_attributes(handle: int) -> int:
    ctypes, wintypes, kernel32, _ntdll, _UnicodeString, _ObjectAttributes, _IoStatusBlock, FileAttributeTagInfo = _windows_api()
    info = FileAttributeTagInfo()
    if not kernel32.GetFileInformationByHandleEx(
        wintypes.HANDLE(handle),
        _WIN_FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(info.FileAttributes)


def _windows_close_handle(handle: int | None) -> None:
    if handle is None:
        return
    _ctypes, wintypes, kernel32, *_ = _windows_api()
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _open_windows_workspace(workspace: Path) -> int:
    ctypes, wintypes, kernel32, *_ = _windows_api()
    path = os.path.abspath(os.fspath(workspace))
    access = (
        _WIN_FILE_LIST_DIRECTORY | _WIN_FILE_TRAVERSE
        | _WIN_FILE_READ_ATTRIBUTES | _WIN_SYNCHRONIZE
    )
    # Omitting FILE_SHARE_DELETE pins the workspace root against rename/delete
    # until the complete staging operation releases its handle.
    handle = kernel32.CreateFileW(
        path,
        access,
        _WIN_FILE_SHARE_READ | _WIN_FILE_SHARE_WRITE,
        None,
        _WIN_OPEN_EXISTING,
        _WIN_FILE_FLAG_BACKUP_SEMANTICS | _WIN_FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle is None or handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    raw = int(handle)
    try:
        attributes = _windows_file_attributes(raw)
        if attributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError("Workspace root cannot be a reparse point")
        if not attributes & _WIN_FILE_ATTRIBUTE_DIRECTORY:
            raise NotADirectoryError(errno.ENOTDIR, "Workspace root is not a directory", path)
        return raw
    except Exception:
        _windows_close_handle(raw)
        raise


def _write_windows_native(workspace: Path, folders: tuple[str, ...], filename: str,
                          data: bytes, *, create_workspace: bool,
                          crash_after_write: bool) -> str:
    """Create the stage through pinned Windows directory handles only."""
    import msvcrt

    if create_workspace:
        # Workspace creation is setup; the subsequent handle open rejects a
        # reparse-point workspace and pins the resulting directory for writes.
        workspace.mkdir(parents=True, exist_ok=True)

    directory_handles: list[int] = []
    file_handle: int | None = None
    try:
        parent = _open_windows_workspace(workspace)
        directory_handles.append(parent)

        directory_access = (
            _WIN_FILE_LIST_DIRECTORY | _WIN_FILE_TRAVERSE
            | _WIN_FILE_READ_ATTRIBUTES | _WIN_SYNCHRONIZE
        )
        directory_options = (
            _WIN_FILE_DIRECTORY_FILE | _WIN_FILE_OPEN_REPARSE_POINT
            | _WIN_FILE_SYNCHRONOUS_IO_NONALERT
        )
        for part in folders:
            child = _nt_create_file_relative(
                parent, part,
                desired_access=directory_access,
                share_access=_WIN_FILE_SHARE_READ | _WIN_FILE_SHARE_WRITE,
                disposition=_WIN_FILE_OPEN_IF,
                create_options=directory_options,
            )
            try:
                attributes = _windows_file_attributes(child)
                if attributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
                    raise OSError(f"Staging directory {part!r} is a reparse point")
                if not attributes & _WIN_FILE_ATTRIBUTE_DIRECTORY:
                    raise NotADirectoryError(errno.ENOTDIR, "Staging component is not a directory", part)
            except Exception:
                _windows_close_handle(child)
                raise
            directory_handles.append(child)
            parent = child

        file_access = (
            _WIN_FILE_READ_DATA | _WIN_FILE_WRITE_DATA
            | _WIN_FILE_READ_ATTRIBUTES | _WIN_SYNCHRONIZE
        )
        file_options = (
            _WIN_FILE_NON_DIRECTORY_FILE | _WIN_FILE_OPEN_REPARSE_POINT
            | _WIN_FILE_SYNCHRONOUS_IO_NONALERT
        )
        try:
            file_handle = _nt_create_file_relative(
                parent, filename,
                desired_access=file_access,
                share_access=0,
                disposition=_WIN_FILE_CREATE,
                create_options=file_options,
            )
            created = True
        except FileExistsError:
            file_handle = _nt_create_file_relative(
                parent, filename,
                desired_access=_WIN_FILE_READ_DATA | _WIN_FILE_READ_ATTRIBUTES | _WIN_SYNCHRONIZE,
                share_access=0,
                disposition=_WIN_FILE_OPEN,
                create_options=file_options,
            )
            created = False

        attributes = _windows_file_attributes(file_handle)
        if attributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError("Existing immutable stage cannot be a reparse point")
        if attributes & _WIN_FILE_ATTRIBUTE_DIRECTORY:
            raise IsADirectoryError(errno.EISDIR, "Immutable stage path is a directory", filename)

        fd_flags = os.O_BINARY | (os.O_RDWR if created else os.O_RDONLY)
        fd = msvcrt.open_osfhandle(file_handle, fd_flags)
        file_handle = None  # The CRT descriptor now owns the native handle.
        mode = "w+b" if created else "rb"
        try:
            stream = os.fdopen(fd, mode)
        except Exception:
            os.close(fd)
            raise

        with stream:
            if created:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                if crash_after_write:
                    os._exit(79)
                stream.seek(0)
            actual = stream.read(len(data) + 1)

        if actual != data:
            raise ImmutableStageConflict("Staged file readback differs")
        return hashlib.sha256(actual).hexdigest()
    finally:
        if file_handle is not None:
            _windows_close_handle(file_handle)
        for handle in reversed(directory_handles):
            _windows_close_handle(handle)


def stage_immutable(workspace: Path, folders: tuple[str, ...] | list[str],
                    filename: str, data: bytes, *,
                    create_workspace: bool = False,
                    crash_after_write: bool = False) -> str:
    """Create-once, replay-idempotent, byte-compared local stage.

    The immutable file's content may be generated by an untrusted planner, but
    this writer never executes or interprets it. Caller owns task/grant locks.
    """
    workspace = Path(workspace)
    folders = tuple(_single_component(item) for item in folders)
    filename = _single_component(filename)
    if not isinstance(data, bytes):
        raise ValueError("Stage requires exact immutable bytes")
    if os.name == "nt":
        return _write_windows_native(
            workspace, folders, filename, data,
            create_workspace=create_workspace,
            crash_after_write=crash_after_write,
        )
    if workspace.is_symlink():
        raise OSError("Workspace cannot be a symlink")
    if create_workspace:
        workspace.mkdir(parents=True, exist_ok=True)
    if not workspace.is_dir():
        raise OSError("Workspace directory does not exist")
    return _write_posix(
        workspace, folders, filename, data,
        crash_after_write=crash_after_write,
    )
