"""Create a bounded CAOS -> Video Studio handoff from already-reviewed source inputs.

This is a structural compiler, never an LLM reasoning engine, authority source,
permission grant, or proof of native ChatGPT Skill selection. The parent must
perform real research/decision/authorization before calling it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


class ChildHandoffError(ValueError):
    pass


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _list_of_strings(value: Any, *, nonempty: bool = False) -> bool:
    return (isinstance(value, list) and (not nonempty or bool(value))
            and all(isinstance(item, str) and item.strip() for item in value))


def compile_video_handoff(project_id: str, brief: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Bind an owner/decision draft to the exact Video-owned project brief.

    A structurally valid handoff MUST NOT be interpreted as authority validation.
    """
    if not isinstance(project_id, str) or not project_id or len(project_id) > 80:
        raise ChildHandoffError("explicit Video project ID required")
    if not isinstance(brief, dict) or not isinstance(draft, dict):
        raise ChildHandoffError("brief and parent draft must be objects")
    gov = brief.get("governance")
    if not isinstance(gov, dict) or gov.get("mode") != "CAOS_PARENT" or gov.get("parent_system") != "cognition-agent-os":
        raise ChildHandoffError("target brief must explicitly select CAOS_PARENT")
    if not isinstance(brief.get("goal"), str) or not brief["goal"].strip():
        raise ChildHandoffError("target brief has no owner goal")
    if not _list_of_strings(brief.get("success_criteria"), nonempty=True):
        raise ChildHandoffError("target brief needs owner success criteria")
    allowed = gov.get("allowed_effects")
    if not _list_of_strings(allowed, nonempty=True) or len(set(allowed)) != len(allowed):
        raise ChildHandoffError("target brief needs a bounded effect scope")

    required = {
        "owner_goal_ref", "owner_corrections", "source_refs", "decision",
        "allowed_effects", "verification", "unknowns",
    }
    if set(draft) != required:
        raise ChildHandoffError("draft must supply exactly the authorized decision fields")
    if not isinstance(draft["owner_goal_ref"], str) or not draft["owner_goal_ref"].strip():
        raise ChildHandoffError("owner goal reference missing")
    if not _list_of_strings(draft["owner_corrections"]) or not _list_of_strings(draft["unknowns"]):
        raise ChildHandoffError("owner corrections or unknowns malformed")
    if not _list_of_strings(draft["source_refs"], nonempty=True):
        raise ChildHandoffError("source evidence references required")
    effects = draft["allowed_effects"]
    if not _list_of_strings(effects, nonempty=True) or not set(effects).issubset(set(allowed)):
        raise ChildHandoffError("handoff cannot grant effects outside the Video brief")

    decision = draft["decision"]
    if not isinstance(decision, dict) or any(not decision.get(k) for k in (
            "question", "hypotheses", "alternatives", "selected_option", "falsifier", "rollback")):
        raise ChildHandoffError("incomplete material decision")
    hypos, options = decision["hypotheses"], decision["alternatives"]
    if (not isinstance(hypos, list) or len(hypos) < 2
            or not all(isinstance(x, dict) and x.get("discriminator") for x in hypos)
            or not isinstance(options, list) or len(options) < 2
            or not all(isinstance(x, dict) and x.get("id") for x in options)
            or decision["selected_option"] not in [x["id"] for x in options]):
        raise ChildHandoffError("no competing hypotheses/options with discriminators")
    verification = draft["verification"]
    if (not isinstance(verification, dict)
            or not _list_of_strings(verification.get("owner_outcomes"), nonempty=True)
            or not _list_of_strings(verification.get("independent_evidence"), nonempty=True)):
        raise ChildHandoffError("no owner-result/independent-evidence acceptance")

    return {
        "schema_version": 1,
        "parent_system": "cognition-agent-os",
        "child_system": "video-growth-agent",
        "project_id": project_id,
        "brief_sha256": hashlib.sha256(_json_bytes(brief)).hexdigest(),
        "owner_goal_ref": draft["owner_goal_ref"],
        "goal": brief["goal"],
        "owner_corrections": draft["owner_corrections"],
        "source_refs": draft["source_refs"],
        "decision": decision,
        "allowed_effects": effects,
        "verification": verification,
        "unknowns": draft["unknowns"],
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > 131072:
        raise ChildHandoffError("input JSON missing or over 128 KiB")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ChildHandoffError(f"malformed input JSON: {path.name}") from exc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build CAOS -> Video receipt from reviewed evidence (structural check only)")
    p.add_argument("--project-id", required=True)
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--draft", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        receipt = compile_video_handoff(args.project_id, _read_json(args.brief), _read_json(args.draft))
        # Never overwrite an existing owner-evidence artifact in place.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({
            "receipt": str(args.output), "brief_sha256": receipt["brief_sha256"],
            "assurance": "STRUCTURAL_ONLY_NO_NATIVE_SELECTION_OR_OWNER_OUTCOME",
        }, ensure_ascii=False))
        return 0
    except (ChildHandoffError, OSError) as exc:
        print(f"CAOS child handoff refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
