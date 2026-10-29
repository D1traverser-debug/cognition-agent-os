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
    # The following domains have task-instance state refs, not a canonical
    # global JSON checkpoint. Inspect their native manifest/capability
    # contract, but do NOT invent a business instance or mutable owner state.
    ("financial_writing", "financial-writing-agent", None),
    ("ashare", "a-share-event-driven-agent", None),
)


def call(args: list[str], *, cwd: Path, python_path: Path | None = None,
         extra_env: dict[str, str] | None = None) -> str:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env is not None:
        env.update(extra_env)
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


def video_native_audit(repo: Path, sandbox: Path) -> dict:
    # Execute actual child-owned code, in a disposable checkout. No media API.
    out = call([sys.executable, "-m", "video_growth_agent.cli",
                "system-audit", "--repo-root", str(repo)],
               cwd=repo, python_path=repo)
    verdict = json.loads(out)
    if verdict.get("pass") is not True or verdict.get("failures"):
        raise AssertionError(f"Native video system audit did not pass: {verdict}")
    # A REAL child business state transition in an isolated disposable folder.
    # Do not use a real owner project or child's checkout as the state root.
    isolated = sandbox / "video-native-projects"
    project_id = "cognition-native-sandbox-probe"
    preview = call(
        [sys.executable, "-m", "video_growth_agent.cli", "init",
         project_id, "--title", "Isolated Parent-Child Integration Probe"],
        cwd=repo, python_path=repo,
        extra_env={"VGA_PROJECTS_DIR": str(isolated)})
    cli_result = json.loads(preview)
    state_file = isolated / project_id / "state.json"
    receipt_dir = isolated / project_id / "receipts"
    if not state_file.is_file() or not receipt_dir.is_dir():
        raise AssertionError("Native child did not persist its own sandbox state")
    independent = json.loads(state_file.read_text(encoding="utf-8"))
    if (cli_result.get("project_id") != project_id
        or independent.get("project_id") != project_id
        or independent.get("stage") != "INTAKE"
        or not any(receipt_dir.iterdir())):
        raise AssertionError("Independent state/receipt readback rejected child outcome")
    return {"native_operation": "vga system-audit + sandbox vga init",
            "passed": True, "child_owned_project_id": project_id,
            "child_native_sandbox_state": independent["stage"],
            "child_native_sandbox_receipts_verified": True,
            "real_business_sandbox_effect_verified": True,
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
            state_path = (manifest["domain_authority"][key]
                          if key is not None else None)
            if key is not None and not isinstance(state_path, str):
                raise AssertionError("Child did not declare a real state reference")
            observed_children.append((did, name, sha, key, state_path))
        pinned_children = tuple(observed_children)

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
                        "ref": sha, "domain_id": did}
                if authority_key is not None:
                    spec["state_authority_key"] = authority_key
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
            tick = run_tick(db, ws, fixtures, max_jobs=4)
            reports = {did: audit_domain_contract(db, ws, ids[did])
                       for did in ids}
            # Adversarial negative: a per-article template or Python class
            # is not the currently selected native JSON business instance.
            from cognition_agent_os.domain_contract import (
                DomainContractInvalid, observe_native_domain)
            for did, name, bad_key in (
                ("financial_writing", "financial-writing-agent", "article_identity"),
                ("ashare", "a-share-event-driven-agent", "market_day_state"),
            ):
                selected = next(item for item in pinned_children
                                if item[0] == did)
                bad = {"kind": "domain_contract",
                       "repo": "D1traverser-debug/" + name,
                       "ref": selected[2], "domain_id": did,
                       "state_authority_key": bad_key}
                try:
                    observe_native_domain(bad)
                except DomainContractInvalid as exc:
                    if str(exc) != "CHILD_STATE_AUTHORITY_UNVERIFIABLE":
                        raise
                else:
                    raise AssertionError(
                        "Parent invented a current child task from a template")

        if len(tick["tasks"]) != 4 or any(
            task["status"] != "NEEDS_REVIEW" for task in tick["tasks"]
        ):
            raise AssertionError(f"Parent Host did not observe four children: {tick}")
        # Refuse even disposable child work when parent independent intake
        # has not actually confirmed the scoped original child source.
        for did in ids:
            if reports[did].get("status") != "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED":
                raise AssertionError("Parent child admission evidence not established")
        # Native business sandbox actions only AFTER parent's current-source
        # preflight succeeded on both child-owned source contracts.
        native = {
            "video": video_native_audit(checkouts["video-growth-agent"], root),
            "novel": novel_native_guard(checkouts["novel-writing-agent"]),
        }
        observations = {}
        for did, name, sha, key, path in pinned_children:
            review = reports[did]
            observed = review.get("child_native_state_observation")
            if (review.get("status") != "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED"
                or review.get("legacy_parent_bound") is not True
                or review.get("child_business_result_verified") is not False
                or review.get("parent_replacement_admitted") is not False):
                raise AssertionError(f"Child source binding/admission changed: {review}")
            if path is None:
                if observed is not None:
                    raise AssertionError("Invented native business state for unselected task")
                state_status = "NO_BUSINESS_INSTANCE_SELECTED"
                source_digest = None
            else:
                if not isinstance(observed, dict):
                    raise AssertionError("Missing pinned child native checkpoint")
                actual_state = json.loads(
                    (checkouts[name] / path).read_text(encoding="utf-8"))
                if (observed.get("child_declared_state_ref") != path
                    or observed.get("status_from_child_source")
                        != actual_state.get("status")):
                    raise AssertionError("Independent child state readback mismatch")
                state_status = observed["status_from_child_source"]
                source_digest = observed["state_content_sha256"]
            observations[did] = {
                "repo": name, "sha": sha, "state_path": path,
                "source_sha256": source_digest,
                "status": state_status,
                "independently_reread": True,
                "legacy_parent_bound": True,
                "native_guard": native.get(did, {
                    "native_operation": "READ_ONLY_CONTRACT_NO_BUSINESS_INSTANCE",
                    "business_effect_performed": False}),
                "business_outcome_verified": False,
            }
        for _, name, _, _, _ in pinned_children:
            dirty = call(["git", "status", "--porcelain"], cwd=checkouts[name]).strip()
            if dirty:
                raise AssertionError(f"Child checkout was modified: {name}: {dirty}")
        print(json.dumps({
            "test": "original-host-four-real-child-contracts-two-native-sandbox-holdouts",
            "source": "immutable actual git checkouts, original child code",
            "github_tool_transport_in_live_parent": False,
            "parent_host_runtime": True,
            "child_repositories_modified": False,
            "isolated_native_business_project_created": True,
            "isolated_native_business_project_independently_verified": True,
            "four_live_child_contracts_independently_reobserved": True,
            "production_execution_authorized": False,
            "whole_product_ready": False,
            "children": observations,
        }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
