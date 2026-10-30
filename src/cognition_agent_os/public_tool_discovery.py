"""Bounded public GitHub *metadata search* as an optional research capability.

A public query is a disclosure to GitHub, so it requires a distinct explicit
owner scope. No clone, install, repository contents, shell, credential or
external write. Rankings are *leads*, not security or goal acceptance evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .ledger import readonly_snapshot
from .ledger import current_guard, finalize_observed, renew_claim
from .runner import ArtifactConflict, store_once

_TERMS = re.compile(r"[a-z][a-z0-9-]{2,24}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_MAX_RESPONSE_BYTES = 250_000
_MAX_RESULTS = 5

class PublicDiscoveryInvalid(ValueError):
    pass

class PublicDiscoveryTransport(PublicDiscoveryInvalid):
    pass

def validate_public_discovery(spec: object) -> dict:
    if (not isinstance(spec, dict)
        or set(spec) != {"kind", "scope", "terms"}
        or spec.get("kind") != "public_tool_discovery"
        or spec.get("scope") != "GITHUB_PUBLIC_METADATA_ONLY"
        or not isinstance(spec.get("terms"), list)
        or not 1 <= len(spec["terms"]) <= 4
        or not all(isinstance(t, str) and _TERMS.fullmatch(t)
                   for t in spec["terms"])
        or len(set(spec["terms"])) != len(spec["terms"])):
        raise PublicDiscoveryInvalid("INVALID_PUBLIC_DISCOVERY_CONTRACT")
    return spec

def safe_public_terms(goal: str) -> list[str]:
    """No verbatim objective or arbitrary model-provided URL is sent remotely."""
    if not isinstance(goal, str):
        raise PublicDiscoveryInvalid("INVALID_PUBLIC_DISCOVERY_GOAL")
    stop = {
        "find","the","and","that","with","from","without","which","what",
        "some","best","good","need","want","please","existing","suitable",
        "reliable","open","source","public","based","build","create",
        "search","look","tool","tools","using","help","system","for",
        "our","your","their","would","should","could","able","more",
        "work","working","automatically","software","framework"
    }
    seen = set()
    terms = []
    for t in re.findall(r"[a-z][a-z0-9-]{2,24}", goal.casefold()):
        if t in stop or t in seen:
            continue
        seen.add(t)
        terms.append(t)
        if len(terms) >= 3:
            break
    if not terms:
        raise PublicDiscoveryInvalid("PUBLIC_SEARCH_HAS_NO_SAFE_TERMS")
    return terms

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _search_public_github(terms: list[str]) -> tuple[dict, str]:
    """Fixed host, no redirect, no credentials, at most one bounded GET."""
    validate_public_discovery({
        "kind": "public_tool_discovery",
        "scope": "GITHUB_PUBLIC_METADATA_ONLY", "terms": terms
    })
    url = "https://api.github.com/search/repositories?" + urlencode({
        "q": " ".join(terms), "per_page": str(_MAX_RESULTS), "page": "1",
    })
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "cognition-agent-os-public-tool-discovery",
    }, method="GET")
    try:
        with build_opener(_NoRedirect()).open(req, timeout=12) as response:
            if (response.status != 200
                or response.geturl() != url):
                raise PublicDiscoveryTransport("PUBLIC_SEARCH_REDIRECT_OR_BAD_STATUS")
            data = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(data) > _MAX_RESPONSE_BYTES:
                raise PublicDiscoveryInvalid("PUBLIC_SEARCH_RESPONSE_TOO_LARGE")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        # Even rate-limited responses are UNKNOWN, not 'no tools exist'.
        raise PublicDiscoveryTransport("PUBLIC_SEARCH_UNAVAILABLE") from exc
    try:
        envelope = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise PublicDiscoveryInvalid("PUBLIC_SEARCH_INVALID_RESPONSE") from exc
    return envelope, hashlib.sha256(data).hexdigest()


def _project_results(envelope: object) -> list[dict]:
    if (not isinstance(envelope, dict)
        or envelope.get("incomplete_results") is not False
        or not isinstance(envelope.get("items"), list)
        or len(envelope["items"]) > _MAX_RESULTS):
        raise PublicDiscoveryInvalid("PUBLIC_SEARCH_INCOMPLETE_OR_INVALID")
    result = []
    seen = set()
    for row in envelope["items"]:
        if not isinstance(row, dict):
            raise PublicDiscoveryInvalid("PUBLIC_SEARCH_INVALID_REPO")
        name = row.get("full_name")
        link = row.get("html_url")
        if (not isinstance(name, str) or not _REPO.fullmatch(name)
            or not isinstance(link, str)
            or link != "https://github.com/" + name
            or name in seen or row.get("private") is not False
            or type(row.get("stargazers_count")) is not int
            or row["stargazers_count"] < 0
            or not isinstance(row.get("archived"), bool)):
            raise PublicDiscoveryInvalid("PUBLIC_SEARCH_INVALID_REPO")
        seen.add(name)
        license_obj = row.get("license")
        license_code = (license_obj.get("spdx_id")
                        if isinstance(license_obj, dict) else None)
        if not isinstance(license_code, str) or len(license_code) > 64:
            license_code = None
        description = row.get("description")
        if not isinstance(description, str):
            description = ""
        result.append({
            "repository": name, "url": link, "description": description[:300],
            "stars_observed": row["stargazers_count"],
            "archived": row["archived"], "license_spdx": license_code,
            "research_status": "UNVERIFIED_CANDIDATE",
        })
    return result


def run_public_discovery(db: sqlite3.Connection, task: dict,
                         workspace: Path) -> dict:
    try:
        spec = validate_public_discovery(json.loads(task["source_spec"]))
        # Public search must be explicitly scoped at its original owner goal,
        # not admitted by a model-selected child on its own.
        if task.get("parent_task") is None:
            raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        parent = db.execute("SELECT source_spec FROM tasks WHERE task_id=?",
                            (task["parent_task"],)).fetchone()
        if parent is None:
            raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        original = json.loads(parent["source_spec"])
        if not isinstance(original, dict):
            raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        if original.get("kind") == "native_goal":
            # Native model decisions use the same bounded original scope.
            # A forged native contract or model-created child alone cannot
            # grant permission for an outbound metadata disclosure.
            from .native_decision import _valid_contract
            if not _valid_contract(original):
                raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        elif original.get("kind") != "open_goal":
            raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        if original.get("allow_public_discovery") is not True:
            raise PublicDiscoveryInvalid("MISSING_ORIGINAL_OWNER_GRANT")
        allowed, reason = current_guard(db, task, needs_write=True)
        if not allowed:
            return finalize_observed(db, task, "BLOCKED", error_code=reason)
        if not renew_claim(db, task, lease_seconds=60):
            raise PublicDiscoveryInvalid("PUBLIC_DISCOVERY_LEASE_LOST")
        envelope, raw_digest = _search_public_github(spec["terms"])
        proposals = _project_results(envelope)
        artifact = {
            "task_id": task["task_id"], "goal_rev": task["goal_rev"],
            "query_terms": spec["terms"], "provider": "github-public-search",
            "search_response_sha256": raw_digest,
            "candidate_repositories": proposals,
            "provider_results": envelope,
            "business_outcome_verified": False,
            "provider_security_verified": False,
            "new_tool_execution_authorized": False,
            "next_step": "INDEPENDENTLY_REVIEW_FIT_API_AND_SECURITY",
        }
        body = (json.dumps(artifact, ensure_ascii=False, sort_keys=True,
                           indent=2) + "\n").encode("utf-8")
        if len(body) > 250_000:
            raise PublicDiscoveryInvalid("PUBLIC_SEARCH_RESPONSE_TOO_LARGE")
        result = finalize_observed(
            db, task, "NEEDS_REVIEW",
            decision="PUBLIC_REPO_CANDIDATES_UNREVIEWED",
            artifact_writer=lambda: store_once(workspace, task["task_id"], body))
        return {**result, "business_outcome_verified": False}
    except PublicDiscoveryTransport:
        return finalize_observed(
            db, task, "UNKNOWN", error_code="PUBLIC_SEARCH_UNAVAILABLE")
    except (PublicDiscoveryInvalid, ArtifactConflict, ValueError, TypeError,
            KeyError, OSError):
        return finalize_observed(
            db, task, "UNKNOWN", error_code="PUBLIC_DISCOVERY_UNVERIFIABLE")


def audit_public_discovery(db_path: Path, workspace: Path,
                           task_id: str) -> dict:
    """Independent local artifact readback, not a provider trust or fit oracle."""
    unknown = {"status": "UNVERIFIABLE", "business_outcome_verified": False}
    try:
        with readonly_snapshot(db_path) as db:
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["state"] != "NEEDS_REVIEW":
                return {**unknown, "reason":"TASK_NOT_REVIEWABLE"}
            spec = validate_public_discovery(json.loads(row["source_spec"]))
            from .runner import verify_artifact
            if not verify_artifact(workspace, dict(row)):
                return {**unknown, "reason":"ARTIFACT_HASH_OR_PATH_UNAVAILABLE"}
            path = workspace / "artifacts" / (task_id + ".json")
            obj = json.loads(path.read_bytes())
            if (obj.get("task_id") != task_id or obj.get("goal_rev") != row["goal_rev"]
                or obj.get("query_terms") != spec["terms"]
                or obj.get("provider") != "github-public-search"
                or obj.get("business_outcome_verified") is not False
                or obj.get("provider_security_verified") is not False
                or obj.get("new_tool_execution_authorized") is not False
                or obj.get("next_step") != "INDEPENDENTLY_REVIEW_FIT_API_AND_SECURITY"
                or obj.get("candidate_repositories") !=
                    _project_results(obj.get("provider_results"))):
                return {**unknown, "reason":"PUBLIC_METADATA_RECEIPT_CONTRADICTION"}
            return {"status": "PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED",
                    "count": len(obj["candidate_repositories"]),
                    "business_outcome_verified": False,
                    "provider_security_verified": False}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError,
            PublicDiscoveryInvalid) as exc:
        return {**unknown, "reason":"AUDIT_INPUT_UNAVAILABLE_OR_INVALID",
                "diagnostic_class":type(exc).__name__}
