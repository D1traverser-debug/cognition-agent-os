"""Offline, bounded evidence index. Never reruns tests or certifies an outcome.

Accept native experiment JSON receipts or their downloaded ZIP artifacts.
Emit hashes, reported checks, tool/error counts and token totals; omit prompts,
arguments, replies, reasoning and raw diagnostics. Open the named source only
when a failed check needs investigation. JSONL output can be compared across runs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile

MAX_BYTES = 32 * 1024 * 1024
RECEIPTS = {"native-app-server-model-evidence.json", "native-execution-boundary.json"}
CODE = re.compile(r"\b(?:COGNITION|CLIENT|NATIVE)_[A-Z][A-Z_]{2,80}\b")


def summarize(data, *, locator, digest, artifact_digest=None):
    if not isinstance(data, dict) or not (
        "native_items" in data or "production_entry_preflight" in data
    ):
        raise ValueError("UNRECOGNIZED_NATIVE_RECEIPT")
    checks = data.get("checks")
    valid = (isinstance(checks, dict) and bool(checks)
             and all(isinstance(k, str) and type(v) is bool for k, v in checks.items()))
    status = data.get("status")
    if status not in {"PASS", "FAIL"}:
        raise ValueError("UNRECOGNIZED_REPORTED_STATUS")
    failed = sorted(k for k, v in checks.items() if v is False) if valid else []
    consistency = ("CONTRADICTORY_PASS" if status == "PASS" and (not valid or failed)
                   else "REPORT_ONLY" if valid else "CHECKS_UNAVAILABLE")
    tool_counts, rejected, codes = Counter(), Counter(), Counter()
    items = data.get("native_items", [])
    if not isinstance(items, list):
        raise ValueError("INVALID_NATIVE_ITEMS")
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "mcpToolCall":
            continue
        tool = item.get("tool")
        # Identifiers only; never emit arbitrary model-controlled text fields.
        if not isinstance(tool, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,100}", tool):
            tool = "UNRECOGNIZED_TOOL"
        tool_counts[tool] += 1
        if item.get("status") == "failed" or item.get("error"):
            rejected[tool] += 1
            codes.update(set(CODE.findall(json.dumps(item.get("result"), ensure_ascii=False))))
    failure = data.get("failure")
    codes.update(set(CODE.findall(failure)) if isinstance(failure, str) else [])
    usage = data.get("native_token_usage", [])
    totals = [n for n in usage if type(n) is int and n >= 0] if isinstance(usage, list) else []
    source = data.get("source")
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
        source = None
    return {
        "evidence": locator, "sha256": digest, "artifact_sha256": artifact_digest,
        "source_commit": source, "reported_status": status,
        "interpretation": consistency, "independent_verification": "NOT_PERFORMED",
        "checks_count": len(checks) if valid else None, "failed_checks": failed,
        "tool_calls": dict(sorted(tool_counts.items())),
        "rejected_tool_calls": dict(sorted(rejected.items())),
        "error_codes": dict(sorted(codes.items())),
        "native_total_tokens": max(totals, default=None),
        "cold_recorded_node_count": (len(data["cold_recorded_nodes"])
            if isinstance(data.get("cold_recorded_nodes"), list) else None),
        "product_ready": "NOT_ASSESSED",
    }


def read_receipts(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("MISSING_OR_OVERSIZE_EVIDENCE")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if path.suffix.lower() != ".zip":
        yield summarize(json.loads(raw), locator=str(path), digest=digest)
        return
    # No extraction, basename collisions or path traversal. Every member keeps
    # its archive-qualified identity. Reject duplicates and oversized expansion.
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = [i for i in archive.infolist() if Path(i.filename).name in RECEIPTS]
        if not entries or len(entries) > 8 or len({i.filename for i in entries}) != len(entries):
            raise ValueError("MISSING_OR_AMBIGUOUS_RECEIPT_MEMBERS")
        if sum(i.file_size for i in entries) > MAX_BYTES:
            raise ValueError("OVERSIZE_EXPANDED_EVIDENCE")
        for entry in entries:
            content = archive.read(entry)
            yield summarize(json.loads(content), locator=str(path) + "::" + entry.filename,
                            digest=hashlib.sha256(content).hexdigest(), artifact_digest=digest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args(argv)
    invalid = False
    for path in args.files:
        try:
            rows = list(read_receipts(path))
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            # Do not echo a parser's fragment of private source bytes.
            print(json.dumps({"evidence": str(path), "interpretation": "UNREADABLE",
                              "error_type": type(exc).__name__}))
            invalid = True
            continue
        for row in rows:
            print(json.dumps(row, ensure_ascii=True, sort_keys=True))
            invalid |= row["interpretation"] == "CONTRADICTORY_PASS"
    return 2 if invalid else 0  # Successful indexing is not a passing experiment.


if __name__ == "__main__":
    raise SystemExit(main())
