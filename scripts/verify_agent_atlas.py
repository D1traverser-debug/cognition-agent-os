#!/usr/bin/env python3
"""Fail-closed offline schema/source-coverage check for a PUBLIC research frontier.

A passing check proves an index is internally consistent; it does NOT prove that
the indicated upstream sources were read by a native model, that the links
remain current, or that an owner/business outcome has been achieved.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/research/agent-learning-hub-source-register-20261029.json"
CARDS = ROOT / "docs/research/agent-learning-hub-method-cards-20261029.md"
SHA = re.compile(r"[0-9a-f]{40}\Z")
URLS = re.compile(r"\[[^]]+\]\((https?://[^)]+)\)")
STATES = {"DISCOVERED_NOT_DEEPLY_AUDITED", "SOURCE_ROUTING_AUDITED",
          "SOURCE_AND_CODE_READ", "SOURCE_AND_TEST_READ",
          "SOURCE_AND_METHOD_READ", "SOURCE_AND_BENCHMARK_READ"}

class AtlasError(ValueError):
    pass

def validate(data: dict, *, cards: str, source_readme: str | None = None) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise AtlasError("INVALID_SCHEMA_VERSION")
    atlas = data.get("atlas", {})
    records = data.get("records")
    if (not isinstance(atlas, dict)
            or not isinstance(atlas.get("repository"), str)
            or not SHA.fullmatch(atlas.get("commit", ""))
            or not SHA.fullmatch(atlas.get("readme_blob_sha", ""))
            or not isinstance(records, list) or len(records) != 96
            or atlas.get("url_count") != len(records)):
        raise AtlasError("INVALID_PINNED_ATLAS")
    if "90 **not yet deeply studied**" not in cards:
        raise AtlasError("MISSING_EXPLICIT_UNSTUDIED_BOUNDARY")
    seen, counts = set(), {}
    for record in records:
        if not isinstance(record, dict):
            raise AtlasError("INVALID_RECORD")
        url, state = record.get("url"), record.get("status")
        if (not isinstance(url, str) or not url.startswith("https://")
                or not urlparse(url).netloc or url in seen
                or state not in STATES
                or not isinstance(record.get("label"), str)
                or not isinstance(record.get("atlas_line"), int)
                or record["atlas_line"] < 1):
            raise AtlasError("INVALID_RECORD_OR_DUPLICATE")
        seen.add(url)
        counts[state] = counts.get(state, 0) + 1
        evidence, leads = record.get("evidence"), record.get("nested_leads")
        if not isinstance(evidence, list) or not isinstance(leads, list):
            raise AtlasError("INVALID_EVIDENCE_SHAPE")
        if state == "DISCOVERED_NOT_DEEPLY_AUDITED" and evidence:
            raise AtlasError("INVENTORY_MASQUERADES_AS_STUDY")
        if state != "DISCOVERED_NOT_DEEPLY_AUDITED" and not evidence:
            raise AtlasError("STUDY_HAS_NO_PRIMARY_SOURCE")
        for e in evidence:
            if (not isinstance(e, dict) or not isinstance(e.get("repo"), str)
                    or e["repo"].count("/") != 1
                    or not isinstance(e.get("path"), str) or not e["path"]
                    or not SHA.fullmatch(e.get("blob_sha", ""))
                    or e.get("kind") not in {"redirect_and_boundary", "implementation",
                                             "tests", "docs", "design", "method", "benchmark"}):
                raise AtlasError("UNATTESTED_STUDY_EVIDENCE")
        if any(not isinstance(lead, str) or not lead.startswith("https://")
               or lead == url for lead in leads):
            raise AtlasError("INVALID_NESTED_LEAD")
    if counts.get("DISCOVERED_NOT_DEEPLY_AUDITED") != 90:
        raise AtlasError("CLAIMED_COVERAGE_MISMATCH")
    if source_readme is not None:
        actual_urls = set(URLS.findall(source_readme))
        if actual_urls != seen:
            added, gone = sorted(actual_urls - seen), sorted(seen - actual_urls)
            raise AtlasError(
                f"UPSTREAM_README_LINK_DRIFT: added={added[:5]!r} missing={gone[:5]!r}")
    return {"total": len(records), "source_only": counts["DISCOVERED_NOT_DEEPLY_AUDITED"],
            "source_read": len(records) - counts["DISCOVERED_NOT_DEEPLY_AUDITED"],
            "actual_upstream_links_checked": source_readme is not None,
            "native_skill_trigger_or_user_outcome_tested": False}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--register", type=Path, default=REGISTER)
    p.add_argument("--cards", type=Path, default=CARDS)
    p.add_argument("--readme", type=Path,
                   help="Optional independently fetched live Agent-Learning-Hub README")
    a = p.parse_args()
    data = json.loads(a.register.read_text(encoding="utf-8"))
    cards = a.cards.read_text(encoding="utf-8")
    readme = a.readme.read_text(encoding="utf-8") if a.readme else None
    print(json.dumps(validate(data, cards=cards, source_readme=readme),
                     sort_keys=True))

if __name__ == "__main__":
    main()
