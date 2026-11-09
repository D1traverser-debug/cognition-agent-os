"""Private, verified session snapshots. Restoration never silently restores grants."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from .ledger import readonly_snapshot, connect_existing, event, require_initialized_ledger
from .source import safe_fixture

MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 4096


def export_session(state: Path, destination: Path):
    """SQLite backup API includes committed WAL state; plain file copy does not."""
    require_initialized_ledger(state / "ledger.sqlite")
    if destination.exists():
        raise ValueError("SNAPSHOT_DESTINATION_ALREADY_EXISTS")
    if destination.resolve().is_relative_to(state.resolve()):
        raise ValueError("SNAPSHOT_MUST_BE_OUTSIDE_STATE")
    with tempfile.TemporaryDirectory(prefix="caos-snapshot-") as temp:
        backup = Path(temp) / "ledger.sqlite"
        with readonly_snapshot(state / "ledger.sqlite") as source:
            if source.execute("SELECT 1 FROM events WHERE kind='COGNITION_MANAGED_LEDGER'").fetchone() is None:
                raise ValueError("SNAPSHOT_REQUIRES_MANAGED_LEDGER")
            with closing(sqlite3.connect(backup)) as target:
                source.backup(target)
        files = {"ledger.sqlite": backup.read_bytes()}
        for folder in ("sources", "workspace"):
            base = state / folder
            if not base.is_dir() or base.is_symlink():
                raise ValueError("SNAPSHOT_SOURCE_DIRECTORY_UNSAFE")
            for path in sorted(base.rglob("*")):
                if path.is_symlink():
                    raise ValueError("SNAPSHOT_SYMLINK_REQUIRES_EXPLICIT_REVIEW")
                if path.is_file():
                    rel = path.relative_to(base).as_posix()
                    files[folder + "/" + rel] = safe_fixture(base, rel)
                    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
                        raise ValueError("SNAPSHOT_LIMIT_EXCEEDED")
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("SNAPSHOT_LIMIT_EXCEEDED")
        manifest = {"format": "caos-private-session-v1", "activation": "REQUIRES_OPERATOR_REBIND",
                    "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental replacement of a user's snapshot.
        with destination.open("xb") as out:
            with ZipFile(out, "w", ZIP_DEFLATED) as archive:
                for name, raw in files.items():
                    archive.writestr(name, raw)
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
    return {"status": "PRIVATE_SNAPSHOT_EXPORTED", "file_count": len(files),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "contains_private_goals": True}


def restore_session(archive_path: Path, state: Path):
    """Validate all bytes before publication; refuse overwrite, traversal and bombs."""
    if state.exists() or state.is_symlink():
        raise ValueError("RESTORE_DESTINATION_EXISTS")
    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if (len(names) != len(set(names)) or len(names) > MAX_FILES + 1
                or sum(i.file_size for i in infos) > MAX_BYTES + 1024 * 1024):
            raise ValueError("RESTORE_ARCHIVE_LIMIT_OR_DUPLICATE")
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name
                    or ":" in name or name != path.as_posix()
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or info.flag_bits & 1 or info.is_dir()
                    or not (name in ("manifest.json", "ledger.sqlite")
                            or (len(path.parts) > 1 and path.parts[0] in ("sources", "workspace")))):
                raise ValueError("RESTORE_ARCHIVE_PATH_UNSAFE")
        if "manifest.json" not in names or "ledger.sqlite" not in names:
            raise ValueError("RESTORE_MANIFEST_MISSING")
        manifest = json.loads(archive.read("manifest.json"))
        if (not isinstance(manifest, dict)
                or manifest.get("format") != "caos-private-session-v1"
                or not isinstance(manifest.get("files"), dict)
                or set(manifest["files"]) != set(names) - {"manifest.json"}):
            raise ValueError("RESTORE_MANIFEST_INVALID")
        files = {name: archive.read(name) for name in manifest["files"]}
        for name, raw in files.items():
            if hashlib.sha256(raw).hexdigest() != manifest["files"][name]:
                raise ValueError("RESTORE_HASH_MISMATCH")
    state.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".caos-restore-", dir=state.parent))
    try:
        for name, raw in files.items():
            dest = temporary / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        for folder in ("sources", "workspace"):
            (temporary / folder).mkdir(exist_ok=True)
        require_initialized_ledger(temporary / "ledger.sqlite")
        with closing(connect_existing(temporary / "ledger.sqlite")) as db:
            # Hashes detect damage, not an archive author's intent. A crafted
            # trigger must not delete the restoration fence on insert.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
                raise ValueError("RESTORE_EXECUTABLE_SCHEMA_REJECTED")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("RESTORE_SQLITE_CORRUPT")
            if db.execute("SELECT 1 FROM events WHERE kind='COGNITION_MANAGED_LEDGER'").fetchone() is None:
                raise ValueError("RESTORE_REQUIRES_MANAGED_LEDGER")
            event(db, "operator", "COGNITION_RESTORE_FENCE", {
                "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "effects_require_new_operator_contract": True})
            db.commit()
        # Reserve destination exclusively; a concurrent creator is never replaced.
        state.mkdir(mode=0o700)
        # A partially published state remains fenced and is never auto-retried.
        for name in ("ledger.sqlite", "sources", "workspace"):
            os.replace(temporary / name, state / name)
    finally:
        shutil.rmtree(temporary)
    return {"status": "SESSION_RESTORED_EFFECTS_FENCED", "state": str(state),
            "owner_goal_history_preserved": True, "execution_reauthorized": False}
