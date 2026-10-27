"""Fail closed if an Actions runner tests a synthetic merge instead of PR HEAD.

Unlike workflow-runs filtering by association, this inspects the commit in
the ACTUAL running checkout. Safe for pull_request, push and dispatch.
"""
import json
import os
from pathlib import Path
import re
import subprocess


def expected_sha(event: dict, github_sha: str) -> str:
    pr = event.get("pull_request")
    value = pr.get("head", {}).get("sha") if isinstance(pr, dict) else github_sha
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("no trustworthy expected source SHA in Actions event")
    return value


def verify_checkout(expected: str, actual: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", actual):
        raise ValueError("invalid observed git HEAD")
    if actual != expected:
        raise ValueError(
            "CI_TESTED_WRONG_TREE: expected PR source HEAD "
            + expected + ", observed actual git checkout " + actual
        )
    return {"source_sha_expected": expected,
            "source_sha_observed": actual,
            "scope": "EXACT_SOURCE_REVISION_ONLY_NOT_USER_OUTCOME"}


def main() -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise ValueError("missing GITHUB_EVENT_PATH; not an Actions source attestation")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    expected = expected_sha(event, os.environ.get("GITHUB_SHA", ""))
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    result = verify_checkout(expected, actual)
    print("CI_SOURCE_SHA_ATTESTED " + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
