"""Prove the real PR merge candidate AND its parents, not a GitHub green icon.

GitHub pull_request defaults to refs/pull/<N>/merge; this runner is intentionally
distinct from the original-source-head tests. It makes merge-compatibility loss
visible without treating a synthetic merge as the original Draft HEAD.
"""
import json
import os
from pathlib import Path
import re
import subprocess


def valid_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("invalid Git commit identifier")
    return value


def verify_merge_source(event, event_name, event_sha, actual, ancestry):
    expected = valid_sha(event_sha)
    observed = valid_sha(actual)
    if observed != expected or not ancestry or ancestry[0] != observed:
        raise ValueError("CI_TESTED_WRONG_MERGE: expected " + expected +
                         " observed " + observed)
    if event_name == "pull_request":
        pull = event.get("pull_request")
        if not isinstance(pull, dict):
            raise ValueError("missing PR event payload")
        head = valid_sha(pull.get("head", {}).get("sha"))
        base = valid_sha(pull.get("base", {}).get("sha"))
        if len(ancestry) != 3 or ancestry[1:] != (base, head):
            raise ValueError("CI_MERGE_PARENT_MISMATCH: synthetic PR merge did "
                             "not combine exact event base and Draft HEAD")
        return {"scope": "PR_SYNTHETIC_MERGE",
                "merge_source_sha": observed,
                "base_parent": base,
                "head_parent": head,
                "product_outcome": "NOT_PROVEN"}
    return {"scope": "NON_PR_EXACT_SOURCE_NOT_MERGE",
            "source_sha": observed, "product_outcome": "NOT_PROVEN"}


def main():
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise ValueError("CI run event path missing")
    event = json.loads(Path(path).read_text(encoding="utf-8"))
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                     text=True).strip()
    parents = tuple(subprocess.check_output(
        ["git", "rev-list", "--parents", "-n", "1", "HEAD"],
        text=True).strip().split())
    report = verify_merge_source(event, os.environ.get("GITHUB_EVENT_NAME"),
                                 os.environ.get("GITHUB_SHA", ""),
                                 actual, parents)
    print("CI_MERGE_SOURCE_ATTESTED " + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
