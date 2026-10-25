"""Public upstream contract smoke on CI. No LLM/API key/credential or publication.

A successful run is *one* real upstream read + bounded durable local effect.
It does not validate language-model judgement or continuous autonomous scheduling.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from cognition_agent_os.ledger import connect, create_task, initialize
from cognition_agent_os.runner import verify_artifact
from cognition_agent_os.source import github_public_snapshot, git_blob_sha

UPSTREAM = "modelcontextprotocol/modelcontextprotocol"
PATH = "docs/specification/2026-07-28/changelog.mdx"
OLD_REF = "b488c16623e5202a3961e551886044577ae0f096"
NEW_REF = "db4bfcff3d60f5df01a21bdf6b78f7012cac4634"
OLD_BLOB = "dc5c9a9cf3e6895504534cf3f300514394d8c6ae"
NEW_BLOB = "424b2653ee392eaaede97ec07d35771ad6216c35"


def main() -> int:
    # This test intentionally uses unauthenticated public GitHub REST API; it
    # respects rate limits and refuses to fake a successful upstream fetch.
    old = github_public_snapshot(UPSTREAM, PATH, OLD_REF)
    new = github_public_snapshot(UPSTREAM, PATH, NEW_REF)
    assert git_blob_sha(old) == OLD_BLOB
    assert git_blob_sha(new) == NEW_BLOB
    assert old != new, "Historical source should genuinely differ"
    with tempfile.TemporaryDirectory(prefix="cognition-live-public-") as tmp:
        root = Path(tmp)
        db_path = root / "task.sqlite"
        out = root / "isolated"
        db = connect(db_path)
        initialize(db)
        spec = {"kind": "github", "repo": UPSTREAM, "path": PATH,
                "old_ref": OLD_REF, "new_ref": NEW_REF}
        changed_id = create_task(db, spec)
        db.close()
        # CLI runs in a separate subprocess; this is NOT a cron/scheduler.
        cmd = [sys.executable, "-m", "cognition_agent_os.cli", "--db", str(db_path),
               "--workspace", str(out), "worker-once"]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
        changed = json.loads(result.stdout)
        assert changed["task_id"] == changed_id
        assert changed["status"] == "NEEDS_REVIEW"
        assert changed["decision"] == "CHANGE_REQUIRES_REVIEW"
        db = connect(db_path)
        task = dict(db.execute("SELECT * FROM tasks WHERE task_id=?", (changed_id,)).fetchone())
        assert verify_artifact(out, task), "Actual artifact read-back mismatch"
        assert task["artifact_hash"] is not None
        unchanged_id = create_task(db, {**spec, "new_ref": OLD_REF})
        db.close()
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
        unchanged = json.loads(result.stdout)
        assert unchanged["task_id"] == unchanged_id
        assert unchanged["status"] == "VERIFIED"
        assert unchanged["decision"] == "NO_CHANGE"
        assert not (out / "artifacts" / (unchanged_id + ".json")).exists()
        # Only public metadata, not model tokens/credentials, appear in job logs.
        print(json.dumps({"source_repo": UPSTREAM, "source_path": PATH,
                          "old_ref": OLD_REF, "new_ref": NEW_REF,
                          "old_blob": OLD_BLOB, "new_blob": NEW_BLOB,
                          "positive": changed["decision"], "negative": unchanged["decision"],
                          "readback": "PASS", "planner": "deterministic-no-model",
                          "host_trigger": "github-actions-push-not-schedule"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
