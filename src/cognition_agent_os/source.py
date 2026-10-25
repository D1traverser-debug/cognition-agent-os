"""Read-only, bounded evidence sources. No tool-provided instructions are trusted."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

MAX_SOURCE_BYTES = 1024 * 1024
_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")

_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")


class SourceUnavailable(Exception):
    """No credible upstream evidence was obtained."""

class SourceTransportUnavailable(SourceUnavailable):
    """Retryable transport failure, not an invalid content or missing path."""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _bounded_opened_file(fd: int) -> bytes:
    """Read the already-opened object, never reopen its previously checked path."""
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Fixture is not a regular file")
        if info.st_size > MAX_SOURCE_BYTES:
            raise SourceUnavailable("Fixture too large")
        content = stream.read(MAX_SOURCE_BYTES + 1)
        if len(content) > MAX_SOURCE_BYTES:
            raise SourceUnavailable("Fixture grew beyond size limit")
        return content


def _anchored_posix_fd(base: Path, canonical: Path) -> int:
    """Use dirfd-relative, no-follow traversal to prevent path-swap escapes."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise SourceUnavailable("Race-safe fixture opening unsupported on this host")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(str(base), flags)
    try:
        for part in canonical.parts[:-1]:
            next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(canonical.parts[-1], os.O_RDONLY | os.O_NOFOLLOW,
                       dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _windows_opened_target(fd: int) -> Path:
    """Query the OS handle's final path, not the raceable input path."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    final_name = kernel.GetFinalPathNameByHandleW
    final_name.argtypes = (wintypes.HANDLE, wintypes.LPWSTR,
                           wintypes.DWORD, wintypes.DWORD)
    final_name.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = final_name(msvcrt.get_osfhandle(fd), buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise SourceUnavailable("Cannot verify the opened Windows fixture handle")
    opened = buffer.value
    if opened.startswith("\\\\?\\UNC\\"):
        opened = "\\\\" + opened[8:]
    elif opened.startswith("\\\\?\\"):
        opened = opened[4:]
    return Path(opened).resolve(strict=True)


def safe_fixture(root: Path, relative: str) -> bytes:
    """Return only bytes of a verified in-root regular file, with a hard cap.

    Valid, stable in-root symlinks keep their prior behavior by resolving to a
    canonical relative path first. POSIX follows each canonical component from
    an opened root dirfd with O_NOFOLLOW; Windows separately verifies the
    effective target of the already-opened OS handle. No post-check path reopen.
    """
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Fixture path outside approved root")
    base = root.resolve(strict=True)
    target = (base / relative).resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise ValueError("Fixture path outside approved root")
    canonical = target.relative_to(base)
    try:
        if os.name == "nt":
            fd = os.open(str(target), os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                opened = _windows_opened_target(fd)
                if not opened.is_relative_to(base):
                    raise ValueError("Opened fixture escaped approved root")
            except BaseException:
                os.close(fd)
                raise
        else:
            fd = _anchored_posix_fd(base, canonical)
    except OSError as exc:
        raise SourceUnavailable("Fixture changed or became inaccessible") from exc
    return _bounded_opened_file(fd)


def github_public_snapshot(repo: str, path: str, ref: str) -> bytes:
    """Immutable ref only. Request cannot select URL/host; GitHub Contents API is pinned."""
    if not _REPO_RE.fullmatch(repo) or not _SHA_RE.fullmatch(ref):
        raise ValueError("Repo must be owner/name and ref a full immutable commit SHA")
    if not path or path.startswith("/") or ".." in Path(path).parts or "\\" in path:
        raise ValueError("Unsafe upstream path")
    safe_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
    url = f"https://api.github.com/repos/{repo}/contents/{safe_path}?ref={ref}"
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cognition-agent-os-p1/0.0.1"})
        with urlopen(request, timeout=12) as response:
            payload = response.read(MAX_SOURCE_BYTES * 2 + 1)
        if len(payload) > MAX_SOURCE_BYTES * 2:
            raise SourceUnavailable("GitHub metadata too large")
        doc = json.loads(payload)
        if not isinstance(doc, dict) or doc.get("type") != "file" or doc.get("encoding") != "base64":
            raise SourceUnavailable("GitHub response is not a base64 file")
        content = base64.b64decode(doc["content"], validate=False)
        if len(content) > MAX_SOURCE_BYTES or git_blob_sha(content) != doc.get("sha"):
            raise SourceUnavailable("Invalid content size or GitHub blob SHA")
        return content
    except HTTPError as exc:
        error_type = SourceTransportUnavailable if exc.code in (408, 429, 500, 502, 503, 504) else SourceUnavailable
        raise error_type(f"GitHub HTTP failure: {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceTransportUnavailable(f"GitHub transport unavailable: {type(exc).__name__}") from exc
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SourceUnavailable(f"GitHub response invalid: {type(exc).__name__}") from exc


def get_pair(spec: dict, fixture_root: Path) -> tuple[bytes, bytes, dict]:
    kind = spec.get("kind")
    if kind == "fixture":
        old = safe_fixture(fixture_root, spec["old"])
        new = safe_fixture(fixture_root, spec["new"])
        identity = {"kind": "fixture", "old": spec["old"], "new": spec["new"]}
    elif kind == "github":
        old = github_public_snapshot(spec["repo"], spec["path"], spec["old_ref"])
        new = github_public_snapshot(spec["repo"], spec["path"], spec["new_ref"])
        identity = {"kind": "github", "repo": spec["repo"], "path": spec["path"], "old_ref": spec["old_ref"], "new_ref": spec["new_ref"]}
    else:
        raise ValueError("Unsupported source kind")
    return old, new, {**identity, "old_blob": git_blob_sha(old), "new_blob": git_blob_sha(new),
                      "old_sha256": hashlib.sha256(old).hexdigest(), "new_sha256": hashlib.sha256(new).hexdigest()}


def github_public_branch_head(repo: str, branch: str) -> str:
    """Resolve a public GitHub single-segment branch to immutable full commit SHA.

    This is a mutable *observation*, not a stable evidence ref. Only the full
    SHA returned here may be put into worker jobs.
    """
    if not _REPO_RE.fullmatch(repo) or not _BRANCH_RE.fullmatch(branch) or ".." in branch or branch.endswith(".lock"):
        raise ValueError("Invalid public repository or branch")
    url = f"https://api.github.com/repos/{repo}/branches/{quote(branch, safe='')}"
    request = Request(url, headers={"Accept": "application/vnd.github+json",
                                   "User-Agent": "cognition-agent-os-p3/0.0.1"})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(32769)
        if len(raw) > 32768:
            raise SourceUnavailable("Branch metadata exceeds limit")
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get("commit"), dict):
            raise SourceUnavailable("Branch metadata was not the expected object")
        sha = obj["commit"].get("sha")
        if obj.get("name") != branch or not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            raise SourceUnavailable("Branch metadata identity mismatch")
        return sha
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
        raise SourceUnavailable("Public branch head unavailable or invalid") from exc


def github_public_branch_head_nested(repo: str, branch: str) -> str:
    """Read-only public Git ref of a safe multi-segment branch.

    Kept distinct from the original single-segment watcher adapter so this
    broader name syntax does not silently expand watch-source permissions.
    """
    if (not isinstance(repo, str) or not _REPO_RE.fullmatch(repo)
        or not isinstance(branch, str) or not 1 <= len(branch) <= 128
        or branch.startswith("/") or branch.endswith("/")
        or "\\" in branch or "//" in branch
        or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part)
               or part in (".", "..") or part.endswith(".lock")
               for part in branch.split("/"))):
        raise ValueError("Invalid nested public GitHub branch")
    safe_branch = "/".join(quote(part, safe="") for part in branch.split("/"))
    url = f"https://api.github.com/repos/{repo}/git/ref/heads/{safe_branch}"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "cognition-agent-os-continuity/0.0.1"})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(32769)
        if len(raw) > 32768:
            raise SourceUnavailable("Branch ref metadata exceeds limit")
        obj = json.loads(raw)
        expected = "refs/heads/" + branch
        sha = obj.get("object", {}).get("sha") if isinstance(obj, dict) else None
        kind = obj.get("object", {}).get("type") if isinstance(obj, dict) else None
        if (not isinstance(obj, dict) or obj.get("ref") != expected
            or kind != "commit" or not isinstance(sha, str)
            or not _SHA_RE.fullmatch(sha)):
            raise SourceUnavailable("Branch ref identity mismatch")
        return sha
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            TypeError, KeyError) as exc:
        raise SourceUnavailable("Public nested branch head unavailable") from exc
