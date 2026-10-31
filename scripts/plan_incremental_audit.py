#!/usr/bin/env python3
"""Read-only delta audit. Reuse exact-blob prior evidence, not its authority.

Do not call a matching SHA a new source read, a semantic proof or a grant.
The baseline is public code only; no private source text is ingested.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "caos-blob-audit-baseline-v1"
RECEIPT = "SOURCE_FETCHED_STRUCTURAL_REVIEW_ONLY"
SHA = re.compile(r"[0-9a-f]{40}\Z")

class AuditInputError(ValueError):
    pass


def _blobs_from_baseline(data: dict) -> dict[str, str]:
    if (not isinstance(data, dict) or data.get("schema") != SCHEMA
        or data.get("authority") != "PUBLIC_SOURCE_READ_RECEIPT_NOT_EXECUTION_GRANT"
        or not SHA.fullmatch(str(data.get("ref", "")))
        or not SHA.fullmatch(str(data.get("git_tree_sha", "")))
        or not isinstance(data.get("files"), list)):
        raise AuditInputError("UNTRUSTED_BASELINE")
    result = {}
    for row in data["files"]:
        if (not isinstance(row, dict) or row.get("receipt") != RECEIPT
            or not isinstance(row.get("path"), str)
            or not row["path"] or row["path"].startswith("/")
            or ".." in row["path"].split("/")
            or not SHA.fullmatch(str(row.get("blob_sha", "")))
            or row["path"] in result):
            raise AuditInputError("INVALID_OR_DUPLICATE_RECEIPT")
        result[row["path"]] = row["blob_sha"]
    if not result:
        raise AuditInputError("EMPTY_BASELINE")
    return result


def _blobs_from_tree(data: dict) -> dict[str, str]:
    if (not isinstance(data, dict) or data.get("truncated") is not False
        or not SHA.fullmatch(str(data.get("sha", "")))
        or not isinstance(data.get("tree"), list)):
        raise AuditInputError("TREE_MISSING_OR_TRUNCATED")
    result = {}
    for row in data["tree"]:
        if not isinstance(row, dict) or row.get("type") not in ("tree", "blob"):
            raise AuditInputError("INVALID_TREE_ENTRY")
        if row["type"] != "blob":
            continue
        path, blob_sha = row.get("path"), row.get("sha")
        if (not isinstance(path, str) or not path or path.startswith("/")
            or ".." in path.split("/") or path in result
            or not SHA.fullmatch(str(blob_sha))):
            raise AuditInputError("INVALID_OR_DUPLICATE_CURRENT_BLOB")
        result[path] = blob_sha
    return result


def plan(baseline: dict, current: dict, *, repository: str) -> dict:
    if repository != baseline.get("repository"):
        raise AuditInputError("REPOSITORY_MISMATCH")
    before = _blobs_from_baseline(baseline)
    now = _blobs_from_tree(current)
    reused = sorted(p for p in before.keys() & now.keys() if before[p] == now[p])
    changed = sorted(p for p in before.keys() & now.keys() if before[p] != now[p])
    added = sorted(now.keys() - before.keys())
    retired = sorted(before.keys() - now.keys())
    return {
        "status": "SOURCE_DELTA_CALCULATED_NOT_SEMANTIC_VERIFICATION",
        "repository": repository,
        "baseline_ref": baseline["ref"],
        "current_tree_sha": current["sha"],
        "summary": {
            "reuse_prior_structural_receipt_only": len(reused),
            "changed_requires_read": len(changed),
            "new_requires_read": len(added),
            "retired_requires_lifecycle_review": len(retired),
        },
        "reuse_prior_structural_receipt_only": reused,
        "changed_requires_read": changed,
        "new_requires_read": added,
        "retired_requires_lifecycle_review": retired,
        "semantic_understanding_verified": False,
        "client_or_business_outcome_verified": False,
    }


def _git_tree(root: Path) -> dict:
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, check=True).stdout.decode().strip()
        tree_sha = subprocess.run(["git", "-C", str(root), "rev-parse", head + "^{tree}"],
                                  capture_output=True, check=True).stdout.decode().strip()
        output = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "-z", head],
                                capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise AuditInputError("CURRENT_CHECKOUT_UNAVAILABLE") from e
    if not SHA.fullmatch(head) or not SHA.fullmatch(tree_sha):
        raise AuditInputError("INVALID_CURRENT_GIT_HEAD")
    items = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, name = entry.split(b"\t", 1)
            _, type_, sha = metadata.decode("ascii").split(" ")
            path = name.decode("utf-8")
        except (ValueError, UnicodeError) as e:
            raise AuditInputError("INVALID_GIT_TREE_ROW") from e
        if type_ != "blob":
            raise AuditInputError("UNSUPPORTED_GIT_ENTRY")
        items.append({"path": path, "type": "blob", "sha": sha})
    return {"sha": tree_sha, "truncated": False, "tree": items, "commit": head}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--repository", required=True)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--current-tree", type=Path, help="Untruncated GitHub git/trees JSON")
    source.add_argument("--checkout", type=Path, help="Existing git checkout; no network")
    args = ap.parse_args()
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = (json.loads(args.current_tree.read_text(encoding="utf-8"))
                   if args.current_tree else _git_tree(args.checkout))
        result = plan(baseline, current, repository=args.repository)
    except (AuditInputError, OSError, ValueError) as e:
        ap.exit(2, "SOURCE_DELTA_UNKNOWN: " + str(e) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
