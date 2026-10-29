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
    nested_records = data.get("nested_records", [])
    if (not isinstance(atlas, dict)
            or not isinstance(atlas.get("repository"), str)
            or not SHA.fullmatch(atlas.get("commit", ""))
            or not SHA.fullmatch(atlas.get("readme_blob_sha", ""))
            or not isinstance(records, list) or len(records) != 96
            or not isinstance(nested_records, list)
            or atlas.get("url_count") != len(records)):
        raise AtlasError("INVALID_PINNED_ATLAS")
    if "**not yet deeply studied**" not in cards:
        raise AtlasError("MISSING_EXPLICIT_UNSTUDIED_BOUNDARY")
    # Keep the 96 first-hop README links immutable as a pinned corpus; recursive
    # discoveries are separate nodes, never appended to the README's URL claim.
    # Each canonical URL occurs once even when multiple sources link to it.
    all_records = records + nested_records
    seen, counts = set(), {}
    for idx, record in enumerate(all_records):
        if not isinstance(record, dict):
            raise AtlasError("INVALID_RECORD")
        first_hop = idx < len(records)
        url, state = record.get("url"), record.get("status")
        if (not isinstance(url, str) or not url.startswith("https://")
                or not urlparse(url).netloc or url in seen
                or state not in STATES
                or not isinstance(record.get("label"), str) or not record["label"]
                or (first_hop and (not isinstance(record.get("atlas_line"), int)
                    or record["atlas_line"] < 1))
                or (not first_hop and "atlas_line" in record)):
            raise AtlasError("INVALID_RECORD_OR_DUPLICATE")
        seen.add(url)
        if first_hop:
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
        required_kinds = {
            "SOURCE_ROUTING_AUDITED": {"redirect_and_boundary"},
            "SOURCE_AND_CODE_READ": {"implementation"},
            "SOURCE_AND_TEST_READ": {"tests"},
            "SOURCE_AND_METHOD_READ": {"design", "method"},
            "SOURCE_AND_BENCHMARK_READ": {"benchmark"},
        }.get(state)
        if required_kinds and not required_kinds.intersection(e["kind"] for e in evidence):
            raise AtlasError("STUDY_STATUS_UNSUPPORTED_BY_EVIDENCE")
        # Evidence attached to a GitHub project must originate from that
        # project, unless a pinned redirect/boundary record explicitly
        # explains an upstream repository migration (e.g. OpenHands).
        # A valid blob SHA from an unrelated repo is NOT study evidence.
        parsed_url = urlparse(url)
        route = parsed_url.path.strip("/").split("/")
        if (parsed_url.netloc.lower() == "github.com"
                and len(route) >= 2 and state != "DISCOVERED_NOT_DEEPLY_AUDITED"):
            origin = (route[0] + "/" + route[1]).lower()
            if not (any(e["repo"].lower() == origin for e in evidence)
                    or any(e["kind"] == "redirect_and_boundary"
                           and e["repo"].split("/")[-1].lower() == route[1].lower()
                           for e in evidence)):
                raise AtlasError("STUDY_EVIDENCE_SOURCE_MISMATCH")
        if any(not isinstance(lead, str) or not lead.startswith("https://")
               or lead == url for lead in leads):
            raise AtlasError("INVALID_NESTED_LEAD")
    by_url = {r["url"]: r for r in all_records}
    nested_urls = {r["url"] for r in nested_records}
    leads = {lead for r in all_records for lead in r["nested_leads"]}
    if leads != nested_urls:
        raise AtlasError("NESTED_LEAD_MISSING_OR_UNLINKED_RECORD")
    # Traversal must reach every nested entry from a pinned README root.
    # A URL may appear in multiple link paths, but is learned only once.
    visited = {r["url"] for r in records}
    frontier = list(visited)
    while frontier:
        parent = by_url[frontier.pop()]
        for child in parent["nested_leads"]:
            if child not in visited:
                visited.add(child)
                frontier.append(child)
    if visited != seen:
        raise AtlasError("NESTED_ORPHAN_OR_UNREACHABLE")
    if source_readme is not None:
        actual_urls = set(URLS.findall(source_readme))
        root_urls = {r["url"] for r in records}
        if actual_urls != root_urls:
            added, gone = sorted(actual_urls - root_urls), sorted(root_urls - actual_urls)
            raise AtlasError(
                f"UPSTREAM_README_LINK_DRIFT: added={added[:5]!r} missing={gone[:5]!r}")
    source_only = counts.get("DISCOVERED_NOT_DEEPLY_AUDITED", 0)
    nested_read = sum(r["status"] != "DISCOVERED_NOT_DEEPLY_AUDITED"
                      for r in nested_records)
    return {"total": len(records), "source_only": source_only,
            "source_read": len(records) - source_only,
            "nested_total": len(nested_records),
            "nested_read": nested_read,
            "nested_frontier": len(nested_records) - nested_read,
            "all_total": len(all_records),
            "all_read": len(records) - source_only + nested_read,
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
