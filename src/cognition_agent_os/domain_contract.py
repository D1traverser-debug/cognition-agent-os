"""Registered read-only native CHILD contract inspection within the one Host.

This is a parent-to-child DISCOVERY/ADMISSION OBSERVATION, not migration,
delegated business execution, parent authority, or business result proof.
GitHub snapshots are immutable commit pinned and git-blob checked by source.py.
No child repo or child state is written.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .ledger import readonly_snapshot
from .source import github_public_snapshot, SourceUnavailable, SourceTransportUnavailable
from .ledger import finalize_observed, require_initialized_ledger
from .runner import store_once, verify_artifact

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_ID = re.compile(r"[a-z][a-z0-9_]{1,79}\Z")
FILES = (".uaos/MANIFEST.json", ".uaos/ADAPTER.json", ".uaos/CAPABILITIES.json")
MAX_DOC = 256 * 1024
MAX_ENTRYPOINT_PATH = 160
_STATE_AUTHORITY_KEY = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_STATE_REF = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.json\Z")


class DomainContractInvalid(ValueError):
    pass


_HISTORICAL_PARENT = "D1traverser-debug/universal-agent-os"


def _legacy_parent_ref_paths(manifest: dict, adapter: dict, caps: dict) -> list[str]:
    """Report normative parent references, not incidental UAOS prose.

    A manifest.controller change is not migration while the child's
    declared common capability references point to the old parent.
    Child Skill paths are compatibility, not parent authority.
    """
    refs = []
    for prefix, fields in (
        ("manifest", manifest),
        ("manifest.binding", manifest.get("binding")),
        ("adapter", adapter),
        ("capabilities", caps),
    ):
        if not isinstance(fields, dict):
            continue
        for name, value in fields.items():
            if (isinstance(name, str) and isinstance(value, str)
                and (prefix == "manifest.binding"
                     or name in ("controller", "parent_control_plane")
                     or "ref" in name or "authority" in name)
                and value.startswith(_HISTORICAL_PARENT)):
                refs.append(f"{prefix}.{name}")
    # A URL-only rename is not a child migration.  The four real child
    # adapters also encode parent governance in typed authority/status fields,
    # capabilities' inheritance semantics, and explicit required methods.
    # These are operative declarations, unlike inert UAOS_SKILL.md filenames
    # or historical notes.  Report them without granting any cutover.
    for prefix, fields in (
        ("manifest", manifest),
        ("adapter", adapter),
        ("capabilities", caps),
    ):
        if not isinstance(fields, dict):
            continue
        for name, value in fields.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            if (name in ("status", "binding_status")
                and value == "UAOS_CONTROL_PLANE_ACTIVE"):
                refs.append(f"{prefix}.{name}")
            elif ((name.endswith("_authority")
                   or name.endswith("_inheritance"))
                  and (value == "UAOS"
                       or value.startswith("UAOS_HOSTED")
                       or value.startswith("UAOS_FOR_PARENT"))):
                refs.append(f"{prefix}.{name}")
    hosted = caps.get("hosted_cognition_semantics")
    if (isinstance(hosted, dict)
        and hosted.get("source") == "CURRENT_UAOS_DELIBERATION_POLICY"):
        refs.append("capabilities.hosted_cognition_semantics.source")
    capabilities = caps.get("capabilities")
    if isinstance(capabilities, list):
        for idx, item in enumerate(capabilities):
            if not isinstance(item, dict):
                continue
            required = item.get("required")
            if isinstance(required, list):
                for dependency_idx, dependency in enumerate(required):
                    if (isinstance(dependency, str)
                        and dependency.startswith("UAOS:")):
                        refs.append(
                            f"capabilities.capabilities[{idx}].required[{dependency_idx}]")
    return sorted(set(refs))


def _skill_entrypoint(manifest: dict) -> str:
    """Resolve only a declared, repo-local child entrypoint; never a URL."""
    skill = manifest.get("skill")
    path = skill.get("entrypoint") if isinstance(skill, dict) else None
    if (not isinstance(path, str) or not path or len(path) > MAX_ENTRYPOINT_PATH
        or "\\" in path or path.startswith("/") or not path.endswith(".md")
        or any(part in ("", ".", "..") for part in path.split("/"))):
        raise DomainContractInvalid("CHILD_SKILL_ENTRYPOINT_INVALID")
    return path



def validate_domain_task(spec: dict) -> dict:
    if (not isinstance(spec, dict) or set(spec) not in (
        {"kind", "repo", "ref", "domain_id"},
        {"kind", "repo", "ref", "domain_id", "state_authority_key"}
    ) or spec.get("kind") != "domain_contract"):
        raise DomainContractInvalid("INVALID_DOMAIN_CONTRACT_TASK")
    repo, ref, did = (spec[k] for k in ("repo", "ref", "domain_id"))
    if (not isinstance(repo, str) or not _REPO.fullmatch(repo)
        or not isinstance(ref, str) or not _SHA.fullmatch(ref)
        or not isinstance(did, str) or not _ID.fullmatch(did)):
        raise DomainContractInvalid("INVALID_DOMAIN_CONTRACT_SCOPE")
    if "state_authority_key" in spec:
        key = spec["state_authority_key"]
        if not isinstance(key, str) or not _STATE_AUTHORITY_KEY.fullmatch(key):
            raise DomainContractInvalid("INVALID_CHILD_STATE_AUTHORITY_KEY")
    return dict(spec)


def _state_ref(manifest: dict, spec: dict) -> str | None:
    """Follow an EXACT child-declared canonical JSON reference, not a parent path."""
    key = spec.get("state_authority_key")
    if key is None:
        return None
    authority = manifest.get("domain_authority")
    path = authority.get(key) if isinstance(authority, dict) else None
    if (not isinstance(path, str) or len(path) > 180
        or not _STATE_REF.fullmatch(path)
        or any(part in (".", "..") for part in path.split("/"))
        or path in FILES):
        raise DomainContractInvalid("CHILD_STATE_AUTHORITY_UNVERIFIABLE")
    return path


def _native_contract(documents: dict[str, bytes], spec: dict) -> dict:
    docs = {}
    digests = {}
    for path in FILES:
        raw = documents[path]
        if not isinstance(raw, bytes) or len(raw) > MAX_DOC or not raw:
            raise DomainContractInvalid("CHILD_CONTRACT_NOT_CREDIBLE")
        digests[path] = hashlib.sha256(raw).hexdigest()
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise DomainContractInvalid("CHILD_CONTRACT_NOT_JSON") from exc
        if not isinstance(obj, dict) or obj.get("domain_id") != spec["domain_id"]:
            raise DomainContractInvalid("CHILD_DOMAIN_IDENTITY_MISMATCH")
        docs[path] = obj

    manifest, adapter, caps = (docs[path] for path in FILES)
    entrypoint = _skill_entrypoint(manifest)
    skill = documents.get(entrypoint)
    if not isinstance(skill, bytes) or not skill or len(skill) > MAX_DOC:
        raise DomainContractInvalid("CHILD_SKILL_ENTRYPOINT_UNVERIFIABLE")
    try:
        skill_text = skill.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DomainContractInvalid("CHILD_SKILL_ENTRYPOINT_INVALID") from exc
    if not skill_text.strip():
        raise DomainContractInvalid("CHILD_SKILL_ENTRYPOINT_INVALID")
    digests[entrypoint] = hashlib.sha256(skill).hexdigest()

    state_path = _state_ref(manifest, spec)
    state_observation = None
    if state_path is not None:
        state_raw = documents.get(state_path)
        if not isinstance(state_raw, bytes) or not state_raw or len(state_raw) > MAX_DOC:
            raise DomainContractInvalid("CHILD_NATIVE_STATE_UNVERIFIABLE")
        try:
            state = json.loads(state_raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise DomainContractInvalid("CHILD_NATIVE_STATE_NOT_JSON") from exc
        if (not isinstance(state, dict)
            or not isinstance(state.get("status"), str)
            or not 1 <= len(state["status"]) <= 160):
            raise DomainContractInvalid("CHILD_NATIVE_STATE_NOT_CREDIBLE")
        digests[state_path] = hashlib.sha256(state_raw).hexdigest()
        state_observation = {
            "authority_key": spec["state_authority_key"],
            "child_declared_state_ref": state_path,
            "status_from_child_source": state["status"],
            "status_is_not_parent_business_acceptance": True,
            "state_content_sha256": digests[state_path],
        }

    advertised = caps.get("capabilities")
    ids = [item.get("capability_id") if isinstance(item, dict) else None
           for item in advertised] if isinstance(advertised, list) else []
    if (not ids or any(not isinstance(cid, str) or not _ID.fullmatch(cid)
                       for cid in ids) or len(set(ids)) != len(ids)):
        raise DomainContractInvalid("CHILD_CAPABILITY_DECLARATION_INVALID")
    binding = manifest.get("binding")
    if (not isinstance(binding, dict)
        or binding.get("adapter_ref") != FILES[1]
        or binding.get("capability_ref") != FILES[2]
        or manifest.get("controller") != adapter.get("controller")
        or not isinstance(manifest.get("controller"), str)
        or not isinstance(caps.get("capabilities"), list)
        or not caps["capabilities"]):
        raise DomainContractInvalid("CHILD_NATIVE_BINDING_INVALID")
    # A target domain may legitimately be unknown to today's parent registry;
    # an explicit domain_id is not a grant, nor a reason to invent child state.
    if caps.get("repository") is not None and caps["repository"] != spec["repo"]:
        raise DomainContractInvalid("CHILD_REPOSITORY_MISMATCH")
    legacy_refs = _legacy_parent_ref_paths(manifest, adapter, caps)
    return {
        "kind": "CHILD_CONTRACT_OBSERVATION_V1",
        "repo": spec["repo"],
        "ref": spec["ref"],
        "domain_id": spec["domain_id"],
        "source_sha256": digests,
        "declared_controller": manifest["controller"],
        "manifest_schema": manifest.get("schema_version"),
        "adapter_schema": adapter.get("schema_version"),
        "capability_schema": caps.get("schema_version"),
        "declared_domain_owner": manifest.get("domain_authority"),
        "capability_count": len(ids),
        "advertised_capability_ids": ids,
        "declared_skill_entrypoint": entrypoint,
        "child_native_state_observation": state_observation,
        "advertisement_is_not_execution_grant": True,
        "legacy_parent_binding_refs": legacy_refs,
        "legacy_parent_bound": bool(legacy_refs) or _HISTORICAL_PARENT in manifest["controller"],
        "read_only_source_identity_verified": True,
        "child_business_identity_reissued": False,
        "child_business_state_modified": False,
        "child_business_result_verified": False,
        "parent_replacement_admitted": False,
        "requires_child_native_admission_for_effect": True,
    }


def observe_native_domain(spec: dict) -> dict:
    spec = validate_domain_task(spec)
    docs = {name: github_public_snapshot(spec["repo"], name, spec["ref"])
            for name in FILES}
    try:
        manifest = json.loads(docs[FILES[0]])
        if not isinstance(manifest, dict):
            raise DomainContractInvalid("CHILD_NATIVE_BINDING_INVALID")
        entrypoint = _skill_entrypoint(manifest)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise DomainContractInvalid("CHILD_SKILL_ENTRYPOINT_INVALID") from exc
    docs[entrypoint] = github_public_snapshot(spec["repo"], entrypoint,
                                               spec["ref"])
    state_path = _state_ref(manifest, spec)
    if state_path is not None:
        docs[state_path] = github_public_snapshot(spec["repo"], state_path,
                                                  spec["ref"])
    return _native_contract(docs, spec)


def run_domain_contract(db: sqlite3.Connection, task: dict, workspace: Path) -> dict:
    """Existing Worker's claim/lineage/authority governs a local immutable receipt."""
    try:
        spec = validate_domain_task(json.loads(task["source_spec"]))
    except (ValueError, TypeError, KeyError) as exc:
        return finalize_observed(db, task, "UNKNOWN",
                                 error_code="INVALID_DOMAIN_CONTRACT_TASK")
    try:
        obs = observe_native_domain(spec)
    except SourceTransportUnavailable:
        return finalize_observed(db, task, "UNKNOWN",
                                 error_code="DOMAIN_SOURCE_TRANSPORT_UNKNOWN")
    except (SourceUnavailable, DomainContractInvalid, KeyError,
            TypeError, ValueError, OSError) as exc:
        reason = (str(exc) if isinstance(exc, DomainContractInvalid)
                  else "DOMAIN_SOURCE_UNVERIFIABLE")
        return finalize_observed(db, task, "UNKNOWN", error_code=reason)
    payload = (json.dumps(
        {"task_id": task["task_id"], "goal_rev": task["goal_rev"],
         "grant_rev": task["grant_rev"], "source_spec": spec, "observation": obs,
         "status": "PENDING_INDEPENDENT_DOMAIN_ADMISSION"},
        sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # This writes only inside the already-authorized workspace, under the
    # SAME grant/claim fenced transaction as every other local artifact.
    return finalize_observed(
        db, task, "NEEDS_REVIEW",
        decision="NATIVE_CHILD_CONTRACT_OBSERVED_NOT_ADMITTED",
        artifact_writer=lambda: store_once(workspace, task["task_id"], payload))


def audit_domain_contract(db_path: Path, workspace: Path, task_id: str) -> dict:
    """Independently refetch actual child contracts, not worker's self-claim."""
    require_initialized_ledger(db_path)
    with readonly_snapshot(db_path) as db:
        task = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        authority = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if task is None or task["state"] != "NEEDS_REVIEW":
            return {"status": "NOT_ADMITTED", "reason": "NO_CURRENT_OBSERVATION"}
        if (authority["goal_rev"] != task["goal_rev"] or
            authority["grant_rev"] != task["grant_rev"] or
            not authority["write_allowed"]):
            return {"status": "NOT_ADMITTED", "reason": "AUTHORITY_CHANGED"}
        try:
            spec = validate_domain_task(json.loads(task["source_spec"]))
        except (ValueError, TypeError):
            return {"status": "NOT_ADMITTED", "reason": "INVALID_SOURCE_TASK"}
        if not verify_artifact(workspace, dict(task)):
            return {"status": "NOT_ADMITTED", "reason": "RECEIPT_TAMPERED"}
        receipt_path = workspace / "artifacts" / (task_id + ".json")
        raw = receipt_path.read_bytes()
        try:
            proof = json.loads(raw)
        except ValueError:
            return {"status": "NOT_ADMITTED", "reason": "RECEIPT_INVALID"}
        if (proof.get("task_id") != task_id or proof.get("source_spec") != spec
            or proof.get("goal_rev") != task["goal_rev"]
            or proof.get("grant_rev") != task["grant_rev"]):
            return {"status": "NOT_ADMITTED", "reason": "RECEIPT_IDENTITY_INVALID"}
    try:
        actual = observe_native_domain(spec)
    except (SourceUnavailable, DomainContractInvalid, ValueError, KeyError,
            OSError, TypeError):
        return {"status": "NOT_ADMITTED", "reason": "LIVE_CHILD_CONTRACT_UNVERIFIABLE"}
    if actual != proof.get("observation"):
        return {"status": "NOT_ADMITTED", "reason": "CHILD_CONTRACT_CHANGED"}
    return {
        "status": "CHILD_CONTRACT_INDEPENDENTLY_REOBSERVED",
        "domain_id": spec["domain_id"],
        "repo": spec["repo"],
        "ref": spec["ref"],
        "legacy_parent_bound": actual["legacy_parent_bound"],
        "child_native_state_observation": actual["child_native_state_observation"],
        "child_business_result_verified": False,
        "parent_replacement_admitted": False,
    }
