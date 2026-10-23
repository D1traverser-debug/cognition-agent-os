"""Black-box smoke for the *installed* console entrypoint, not PYTHONPATH tests.

Runs in a throwaway venv and temporary SQLite workspace. Neither production
credentials nor model APIs are used. Tests packaging, cold-resume denial,
local task acceptance, repeated Host tick and independent persisted readback.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    package = importlib.metadata.version("cognition-agent-os")
    binary = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    cli = binary / ("cognition-os.exe" if os.name == "nt" else "cognition-os")
    if not cli.is_file():
        raise SystemExit("INSTALLED_CLI_MISSING")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    with tempfile.TemporaryDirectory(prefix="cognition-installed-smoke-") as root:
        base = Path(root)
        db = base / "tasks.sqlite"
        workspace = base / "artifacts"
        fixtures = base / "fixtures"
        fixtures.mkdir()
        (fixtures / "stable.txt").write_text("unchanged source\n", encoding="utf-8")
        common = [str(cli), "--db", str(db), "--workspace",
                  str(workspace), "--fixtures", str(fixtures)]

        def command(*args, expected=0):
            proc = subprocess.run(
                common + list(args), text=True, capture_output=True,
                env=environment, timeout=35)
            if proc.returncode != expected:
                raise AssertionError(
                    f"CLI {args} returned {proc.returncode}, "
                    f"expected {expected}; stderr={proc.stderr[:300]}, "
                    f"stdout={proc.stdout[:300]}")
            return json.loads(proc.stdout)

        status = command("status")
        assert status["tasks"] == [], status
        assert db.is_file(), "Installed CLI did not initialize durable ledger"

        # A fresh chat/host cannot guess a persisted owner objective.
        missing = command("goal-resume", expected=4)
        assert missing["status"] == "NO_DURABLE_GOAL", missing
        assert "next_task_id" not in missing, missing

        admission = command("seed-fixture", "--old", "stable.txt",
                            "--new", "stable.txt")
        assert admission["state"] == "PENDING", admission

        tick1 = command("host-tick", "--max-jobs", "2")
        assert tick1["processed"] == 1, tick1
        assert tick1["tasks"][0]["status"] == "VERIFIED", tick1
        assert tick1["semantic_outcome_verified"] is False, tick1

        tick2 = command("host-tick", "--max-jobs", "2")
        assert tick2["processed"] == 0, tick2
        assert tick2["status"] == "IDLE", tick2
        status = command("status")
        tasks = [t for t in status["tasks"]
                 if t["task_id"] == admission["task_id"]]
        assert len(tasks) == 1 and tasks[0]["state"] == "VERIFIED", tasks

    print(json.dumps({
        "status": "INSTALLED_CLI_SMOKE_PASS",
        "installed_version": package,
        "entrypoint": cli.name,
        "fresh_goal_no_guess": True,
        "isolated_fixture_verified": True,
        "repeat_host_no_duplicate_work": True,
        "semantic_outcome_verified": False,
        "owner_host_deployed": False,
        "model_api_calls": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
