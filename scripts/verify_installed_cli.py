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

        # Read/status and task submission MUST NOT create a new authority.
        absent_status = command("status", expected=4)
        assert absent_status["status"] == "HOST_NOT_CONFIGURED", absent_status
        absent_seed = command("seed-fixture", "--old", "stable.txt",
                              "--new", "stable.txt", expected=4)
        assert absent_seed["status"] == "HOST_NOT_CONFIGURED", absent_seed
        assert not db.exists(), "Read/seed implicitly created a SQLite grant"
        cold_before = command("goal-resume", expected=4)
        assert cold_before["status"] == "LEDGER_NOT_INITIALIZED"
        assert not db.exists(), "Cold goal resume initialized ledger"

        # The ONLY new-ledger creation is explicit init (local evidence
        # workflow only; not production authorization).
        initialized = command("init")
        assert initialized["status"] == "LOCAL_LEDGER_INITIALIZED", initialized
        assert initialized["local_write_allowed"] is True, initialized
        assert initialized["production_effect_authorized"] is False
        assert db.is_file(), "Explicit init did not create SQLite ledger"
        status = command("status")
        assert status["tasks"] == [], status

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

        # Owner enters a natural-language goal directly through the installed
        # binary, no authored JSON plan or extra authority file. No installed
        # model is called until the real Host is explicitly run in local mode.
        (fixtures / "settings.json").write_text('{"timeout":7}\n',encoding="utf-8")
        open_seed = command(
            "seed-open-goal", "--goal",
            "Please ensure settings.json has owner equal to ops without overwriting timeout.")
        assert open_seed["state"] == "PENDING", open_seed
        assert open_seed["requires_installed_local_model"] is True, open_seed
        assert open_seed["business_outcome_verified"] is False, open_seed
        pending_audit = command("open-goal-audit",
                                "--task-id",open_seed["task_id"], expected=4)
        assert pending_audit["status"] == "UNVERIFIABLE", pending_audit

        revoked = command("revoke-write")
        assert revoked["grant"] == "REVOKED", revoked
        authority_before = command("status")["authority"]
        assert authority_before["write_allowed"] == 0, authority_before
        no_regrant = command("init")
        assert no_regrant["status"] == "ALREADY_INITIALIZED", no_regrant
        assert no_regrant["authority_unchanged"] is True, no_regrant
        authority_after = command("status")["authority"]
        assert authority_before == authority_after, (authority_before, authority_after)

        # An existing corrupt file must not be rebuilt or papered over.
        corrupt = base / "corrupt.sqlite"
        corrupt.write_bytes(b"not sqlite")
        corrupt_common = common[:]
        corrupt_common[corrupt_common.index("--db") + 1] = str(corrupt)
        bad = subprocess.run(corrupt_common + ["init"],
                             text=True,capture_output=True,
                             env=environment, timeout=35)
        assert bad.returncode == 4, (bad.returncode,bad.stdout,bad.stderr)
        assert json.loads(bad.stdout)["status"] == "INITIALIZATION_REFUSED"
        assert corrupt.read_bytes() == b"not sqlite"

    print(json.dumps({
        "status": "INSTALLED_CLI_SMOKE_PASS",
        "installed_version": package,
        "entrypoint": cli.name,
        "fresh_goal_no_guess": True,
        "explicit_init_only": True,
        "existing_revoke_preserved": True,
        "corrupt_ledger_not_reset": True,
        "isolated_fixture_verified": True,
        "repeat_host_no_duplicate_work": True,
        "semantic_outcome_verified": False,
        "owner_host_deployed": False,
        "model_api_calls": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
