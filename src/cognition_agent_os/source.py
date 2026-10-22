"""Read-only, bounded evidence sources. No tool-provided instructions are trusted."""
from __future__ import annotations

import base64
import hashlib
import json
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


def safe_fixture(root: Path, relative: str) -> bytes:
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Fixture path outside approved root")
    base = root.resolve(strict=True)
    target = (base / relative).resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise ValueError("Fixture path outside approved root")
    if target.stat().st_size > MAX_SOURCE_BYTES:
        raise SourceUnavailable("Fixture too large")
    return target.read_bytes()


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
