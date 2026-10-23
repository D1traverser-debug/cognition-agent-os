"""Real public GitHub mutable HEAD -> pinned baseline smoke, no API keys or LLM."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile

from cognition_agent_os.ledger import connect, initialize
from cognition_agent_os.watch import create_watch, observe_one
from cognition_agent_os.source import github_public_branch_head, github_public_snapshot, git_blob_sha

REPO = "D1traverser-debug/cognition-agent-os"
PATH = "README.md"


def main():
    with tempfile.TemporaryDirectory(prefix="cognition-watch-live-") as tmp:
        db_path = Path(tmp) / "tasks.sqlite"
        db = connect(db_path)
        initialize(db)
        watch_id = create_watch(db, REPO, PATH, "main", interval_seconds=1800)
        db.close()
        result = observe_one(db_path, watch_id)
        assert result["status"] == "BASELINED", result
        db = connect(db_path)
        watch = dict(db.execute("SELECT * FROM watch_sources WHERE watch_id=?", (watch_id,)).fetchone())
        count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        db.close()
        assert count == 0, "Initial HEAD is a baseline, never a fake change"
        assert watch["baseline_ref"] == result["current_ref"]
        assert len(watch["baseline_ref"]) == 40
        assert watch["baseline_blob"] and len(watch["baseline_blob"]) == 40
        print(json.dumps({"source": REPO, "path": PATH, "status":result["status"],
                          "pinned_head": watch["baseline_ref"],
                          "blob":watch["baseline_blob"],"enqueued":count,
                          "semantic_verification":"NOT_PERFORMED","model_api_calls":0}, sort_keys=True))


if __name__ == "__main__":
    main()
