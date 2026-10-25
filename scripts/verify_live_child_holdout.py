"""Live native child checkout -> original Host -> independent re-read.

No user data, model calls, child repository writes, release, or runtime grants.
The transport stub reads exact bytes from a Git checkout whose HEAD is verified;
it does NOT invent child manifests, business identities or source outcomes.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from cognition_agent_os.domain_contract import audit_domain_contract
from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize


CHILDREN = (
    ("video", "video-growth-agent", "integrated_default_program"),
    ("novel", "novel-writing-agent", "study_state_ref"),
)


def call(args: list[str], *, cwd: Path, python_path: Path | None = None) -> str:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if python_path is not None:
        env["PYTHONPATH"] = str(python_path)
    proc = subprocess.run(args, cwd=cwd, env=env,
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=130, check=False)
    if proc.returncode:
        raise AssertionError(
            f"Child command returned {proc.returncode}: {args!r}\n"
            + proc.stderr[-3500:] + "\n" + proc.stdout[-1800:])
    return proc.stdout


def original_checkout(root: Path, name: str) -> tuple[Path, str]:
    dest = root / name
    call(["git", "clone", "--quiet", "--depth", "1",
          "https://github.com/D1traverser-debug/" + name + ".git",
          str(dest)], cwd=root)
    got = call(["git", "rev-parse", "HEAD"], cwd=dest).strip()
    if len(got) != 40 or any(c not in "0123456789abcdef" for c in got):
        raise AssertionError(f"Unusable child commit ref: {name}: {got}")
    # Pin the observed current HEAD for every downstream read in THIS run.
    return dest, got


def video_native_audit(repo: Path) -> dict:
    # Execute actual child-owned code, in a disposable checkout. No media API.
    out = call([sys.executable, "-m", "video_growth_agent.cli",
                "system-audit", "--repo-root", str(repo)],
               cwd=repo, python_path=repo)
    verdict = json.loads(out)
    if verdict.get("pass") is not True or verdict.get("failures"):
        raise AssertionError(f"Native video system audit did not pass: {verdict}")
    return {"native_operation": "vga system-audit", "passed": True,
            "business_media_delivered": False}


def novel_native_guard(repo: Path) -> dict:
    # Execute child-native learning admission on an intentionally insufficient
    # evidence packet, proving it rejects fabricated success without writing.
    code = (
        "from runtime.learning_transfer_admission import ("
        "ClosedContextReconstruction,admit_closed_context_reconstruction,"
        "LearningTransferAdmissionError)\n"
        "import json,pathlib\n"
        "s=json.loads(pathlib.Path('research/masterworks/STUDY_STATE.json').read_text())\n"
        "assert isinstance(s.get('status'),str) and s.get('status')\n"
        "try:\n"
        " admit_closed_context_reconstruction(ClosedContextReconstruction("
        "work_id=s.get('active_work',{}).get('work_id') or 'source-state',"
        "compact_index_ref='missing-evidence',recalled_mechanisms=(),"
        "recalled_boundaries=(),missed_or_distorted=(),correction_refs=()))\n"
        "except LearningTransferAdmissionError:\n"
        " print(json.dumps({'guard':'DENIED_UNSUPPORTED_LEARNING',"
        "'status':s['status']}))\n"
        "else:\n"
        " raise AssertionError('Novel native guard admitted unsupported learning')\n"
    )
    out = call([sys.executable, "-c", code], cwd=repo, python_path=repo)
    native = json.loads(out)
    if native["guard"] != "DENIED_UNSUPPORTED_LEARNING":
        raise AssertionError("Novel guard did not fail closed")
    return {"native_operation": "novel learning-transfer admission",
            "rejected_unsupported_evidence": True,
            "business_chapter_was_written": False}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cognition-real-child-") as tmp:
        root = Path(tmp)
        checkouts = {}
        observed_children = []
        for did, name, key in CHILDREN:
            checkout, sha = original_checkout(root, name)
            checkouts[name] = checkout
            manifest = json.loads(
                (checkout / ".uaos/MANIFEST.json").read_text(encoding="utf-8"))
            state_path = manifest["domain_authority"][key]
            if not isinstance(state_path, str):
                raise AssertionError("Child did not declare a real state reference")
            observed_children.append((did, name, sha, key, state_path))
        pinned_children = tuple(observed_children)

        native = {
            "video": video_native_audit(checkouts["video-growth-agent"]),
            "novel": novel_native_guard(checkouts["novel-writing-agent"]),
        }

        db = root / "parent.sqlite"
        ws = root / "parent-work"
        ws.mkdir()
        fixtures = root / "parent-fixtures"
        fixtures.mkdir()
        with closing(connect(db)) as ledger:
            initialize(ledger)
            ids = {}
            for did, name, sha, authority_key, _ in pinned_children:
                spec = {"kind": "domain_contract",
                        "repo": "D1traverser-debug/" + name,
                        "ref": sha, "domain_id": did,
                        "state_authority_key": authority_key}
                ids[did] = create_task(ledger, spec)

        def source(repo: str, path: str, ref: str) -> bytes:
            # Trust ONLY the selected child checked out at the exact SHA.
            for did, name, sha, _, _ in pinned_children:
                if repo == "D1traverser-debug/" + name and ref == sha:
                    base = checkouts[name].resolve()
                    candidate = (base / path).resolve()
                    if not candidate.is_relative_to(base) or not candidate.is_file():
                        raise AssertionError("Child source path escaped pinned checkout")
                    return candidate.read_bytes()
            raise AssertionError("Unapproved child repo/ref")

        with patch("cognition_agent_os.domain_contract.github_public_snapshot",
                   side_effect=source):
            tick = run_tick(db, ws, fixtures, max_jobs=2)
            reports = {did: audit_domain_contract(db, ws, ids[did])
                       for did in ids}

        if len(tick["tasks"]) != 2 or any(
            task["status"] != "NEEDS_REVIEW" for task in tick["tasks"]
        ):
            raise AssertionError(f"Parent Host did not observe two children: {tick}")
        observations = {}
        for did, name, sha, key, path in pinned_children:
            review = reports[did]
            observed = review.get("child_native_state_observation") or {}
            actual_state = json.loads((checkouts[name] / path).read_text(encoding="utf-8"))
            if (review.get("status") != "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED"
                or observed.get("child_declared_state_ref") != path
                or observed.get("status_from_child_source") != actual_state.get("status")
                or review.get("child_business_result_verified") is not False
                or review.get("parent_replacement_admitted") is not False):
                raise AssertionError(f"Child native checkpoint not safe: {review}")
            observations[did] = {
                "repo": name, "sha": sha, "state_path": path,
                "source_sha256": observed["state_content_sha256"],
                "status": observed["status_from_child_source"],
                "independently_reread": True,
                "native_guard": native[did],
                "business_outcome_verified": False,
            }
        for _, name, _, _, _ in pinned_children:
            dirty = call(["git", "status", "--porcelain"], cwd=checkouts[name]).strip()
            if dirty:
                raise AssertionError(f"Child checkout was modified: {name}: {dirty}")
        print(json.dumps({
            "test": "original-host-two-real-child-native-readonly-holdout",
            "source": "immutable actual git checkouts, original child code",
            "github_tool_transport_in_live_parent": False,
            "parent_host_runtime": True,
            "child_repositories_modified": False,
            "production_execution_authorized": False,
            "whole_product_ready": False,
            "children": observations,
        }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
