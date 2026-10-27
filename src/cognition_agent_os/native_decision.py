"""Model-neutral cognition boundary on the existing Host/SQLite authority.

External reasoning (for example the ChatGPT tool loop) can propose the NEXT
bounded registered action against a complete immutable owner goal. Every new
choice uses fresh source and result evidence, a CAS observation fingerprint,
and the same Worker/grant/lineage gateway. This is NOT a model or oracle:
the semantic quality of an option remains unproven until an independent owner
outcome is available. No paid model, second scheduler, plugin installation,
arbitrary code import or production provider effect is implied.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .intent_planner import compile_intent, IntentError
from .ledger import connect, create_task, event, require_initialized_ledger
from .source import safe_fixture, SourceUnavailable

_ID = re.compile(r"[a-f0-9]{32}\Z")
_MAX_DECISIONS = 12
_LEGACY_MAX_DECISIONS = 3
_MAX_HYPOTHESES = 8
_HYPOTHESIS_DISPOSITIONS = frozenset({
    "REJECTED", "CONDITIONALLY_USEFUL", "UNRESOLVED_RESEARCH_REQUIRED",
})
_MAX_SOURCE_COUNT = 64
# Keep original words, including late prohibitions, in ONE canonical SQLite
# contract. The model must refuse an over-budget prompt rather than truncate.
_MAX_ORIGINAL_GOAL_CHARS = 8192
_VALID_KINDS = frozenset({
    "goal_case", "record_reconciliation", "investigate_goal",
    "public_tool_discovery",
})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def _contract(goal: str, *, allow_public_discovery: bool = False,
              legacy: bool = False) -> dict:
    if (not isinstance(goal, str) or not 1 <= len(goal.strip()) <= _MAX_ORIGINAL_GOAL_CHARS
        or type(allow_public_discovery) is not bool
        or type(legacy) is not bool):
        raise ValueError("INVALID_NATIVE_OWNER_GOAL")
    return {"kind": "native_goal", "version": 1 if legacy else 2,
            "goal": goal, "allow_public_discovery": allow_public_discovery,
            "max_decisions": (_LEGACY_MAX_DECISIONS if legacy
                              else _MAX_DECISIONS)}


def _valid_contract(spec: dict) -> bool:
    """Old seeded goals retain their original finite grant and identity."""
    return (isinstance(spec, dict) and spec.get("version") in (1, 2)
            and spec == _contract(spec["goal"],
                                  allow_public_discovery=spec["allow_public_discovery"],
                                  legacy=(spec["version"] == 1)))


def _sources_compatible(pinned: dict, current: dict,
                        selected_kind: str, *,
                        finished: bool = False) -> bool:
    """Append-only knowledge may grow; no pinned historical fact may change.

    Some methods consume the entire corpus of a format rather than named files.
    New material in that format invalidates their original research scope.
    """
    if (not isinstance(pinned, dict)
        or any(current.get(name) != digest for name, digest in pinned.items())):
        return False
    if selected_kind == "investigate_goal" and not finished and any(
            Path(name).suffix.lower() in (".md", ".txt")
            for name in current.keys() - pinned.keys()):
        return False
    return True


def _sources(fixtures: Path) -> dict[str, str]:
    """Bound the complete local evidence corpus, not a model-selected subset."""
    if not fixtures.is_dir() or fixtures.is_symlink():
        raise ValueError("INVALID_NATIVE_SOURCE_ROOT")
    result = {}
    entries = sorted(fixtures.iterdir(), key=lambda p: p.name)
    if len(entries) > _MAX_SOURCE_COUNT:
        raise ValueError("SOURCE_MANIFEST_EXCEEDS_BOUND")
    for path in entries:
        if (not path.is_file() or path.suffix.lower() not in
            (".json", ".csv", ".md", ".txt")):
            raise ValueError("UNSUPPORTED_NATIVE_SOURCE")
        raw = safe_fixture(fixtures, path.name)
        result[path.name] = hashlib.sha256(raw).hexdigest()
    return result


def capability_catalog(fixtures: Path, *, allow_public_discovery: bool = False) -> dict:
    """Current registered methods and source affordances, never model inventing APIs.

    Native ChatGPT/Codex or a later local planner can inspect this before
    proposing two methods. Catalog membership is capability availability, NOT
    proof that either method satisfies the full owner goal.
    """
    from .intent_planner import SUPPORTED_INTENTS, ALLOWED_ROLES
    from .capability_dispatch import _HANDLERS
    manifest = _sources(fixtures)
    files = sorted(manifest)
    suffixes = {x: Path(x).suffix.lower() for x in files}
    kinds = {
        "ensure_structure": "goal_case",
        "compare_records": "record_reconciliation",
        "investigate_evidence": "investigate_goal",
        "discover_public_tools": "public_tool_discovery",
    }
    if set(kinds) != set(SUPPORTED_INTENTS) or not set(kinds.values()).issubset(_HANDLERS):
        raise ValueError("REGISTERED_NATIVE_CATALOG_CHANGED")
    options = []
    for objective in sorted(kinds):
        compatible = (
            [x for x in files if suffixes[x] == ".json"]
            if objective == "ensure_structure"
            else [x for x in files if suffixes[x] == ".csv"]
            if objective == "compare_records"
            else [x for x in files if suffixes[x] in (".md", ".txt")]
            if objective == "investigate_evidence" else []
        )
        available = (
            len(compatible) >= 2 if objective == "compare_records"
            else bool(compatible) if objective in (
                "ensure_structure", "investigate_evidence")
            else allow_public_discovery
        )
        options.append({
            "objective": objective, "task_kind": kinds[objective],
            "required_resource_roles": list(ALLOWED_ROLES[objective]),
            "eligible_sources": compatible,
            "currently_eligible": bool(available),
            "outcome_scope": "MECHANICAL_LOCAL_EVIDENCE_ONLY",
            "business_outcome_verified": False,
            "external_effect_authorized": False,
        })
    return {"status": "NATIVE_CAPABILITY_CATALOG",
            "methods": options, "source_manifest_sha256": _digest(manifest),
            "public_disclosure_authorized": allow_public_discovery,
            "business_outcome_verified": False}


def _selected_sources_present(plan: dict, sources: dict[str, str]) -> bool:
    spec = plan["child_source_spec"]
    kind = spec["kind"]
    if kind == "goal_case":
        return spec["input"] in sources
    if kind == "record_reconciliation":
        return spec["reference"] in sources and spec["observed"] in sources
    if kind == "investigate_goal":
        return any(Path(x).suffix.lower() in (".md", ".txt") for x in sources)
    if kind == "public_tool_discovery":
        return True
    return False


def _proposal(candidate: dict, contract: dict) -> dict:
    """Require independently compilable *competing* local methods.

    Their prose explanations are untrusted model hypotheses. No model-chosen
    module path, shell command, URL or grant is consumed as executor authority.
    """
    base_fields = {"selected_intent", "alternative_intent", "decision_reason",
                   "alternative_reason", "expected_evidence",
                   "observation_sha256", "decision_basis"}
    if (not isinstance(candidate, dict)
        or set(candidate) not in (base_fields,
                                  base_fields | {"hypothesis_reviews"})):
        raise ValueError("UNSUPPORTED_UNGROUNDED_DECISION")
    if (not isinstance(candidate["decision_basis"], dict)
        or set(candidate["decision_basis"]) !=
        {"source_refs", "previous_result_task_id", "challenge", "falsifier",
         "uncertainty"}):
        raise ValueError("UNSUPPORTED_UNGROUNDED_DECISION")
    basis = candidate["decision_basis"]
    for field in ("challenge", "falsifier", "uncertainty"):
        if (not isinstance(basis[field], str)
            or not 12 <= len(basis[field].strip()) <= 500):
            raise ValueError("UNSUPPORTED_UNGROUNDED_DECISION")
    refs = basis["source_refs"]
    if (not isinstance(refs, list) or len(refs) > 16
        or any(not isinstance(v, dict)
               or set(v) != {"path", "sha256"}
               or not isinstance(v["path"], str)
               or not isinstance(v["sha256"], str)
               or not re.fullmatch(r"[0-9a-f]{64}", v["sha256"])
               for v in refs)
        or len({v["path"] for v in refs}) != len(refs)
        or (basis["previous_result_task_id"] is not None
            and (not isinstance(basis["previous_result_task_id"], str)
                 or not _ID.fullmatch(basis["previous_result_task_id"])))):
        raise ValueError("UNSUPPORTED_UNGROUNDED_DECISION")
    fields = ("decision_reason", "alternative_reason", "expected_evidence")
    if any(not isinstance(candidate[x], str) or
           not 8 <= len(candidate[x].strip()) <= 512 for x in fields):
        raise ValueError("MISSING_DECISION_COMPARISON")
    if (not isinstance(candidate["observation_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", candidate["observation_sha256"])):
        raise ValueError("INVALID_OBSERVATION_FINGERPRINT")
    selected = compile_intent(candidate["selected_intent"])
    alternative = (
        compile_intent(candidate["alternative_intent"])
        if candidate["alternative_intent"] is not None else None)
    if alternative is not None and selected["objective"] == alternative["objective"]:
        raise ValueError("COMPETING_METHODS_NOT_DISTINCT")
    if (not contract["allow_public_discovery"]
        and (selected["objective"] == "discover_public_tools"
             or (alternative is not None
                 and alternative["objective"] == "discover_public_tools"))):
        raise PermissionError("PUBLIC_DISCOVERY_NOT_AUTHORIZED")
    if selected["child_source_spec"]["kind"] not in _VALID_KINDS:
        raise ValueError("UNREGISTERED_NATIVE_CAPABILITY")
    return {"selected": selected, "alternative": alternative}


def _method_paths(plan: dict, sources: dict[str, str]) -> set[str]:
    """Observable file obligations for one registered method, not model prose."""
    spec = plan["child_source_spec"]
    kind = spec["kind"]
    if kind == "record_reconciliation":
        return {spec["reference"], spec["observed"]}
    if kind == "goal_case":
        return {spec["input"]}
    if kind == "investigate_goal":
        # The source investigator consumes a bounded local text corpus.
        # Require at least one independently named source in its citation set.
        return set()
    if kind == "public_tool_discovery":
        return set()
    raise ValueError("UNREGISTERED_DECISION_METHOD")


def _ground_decision(candidate: dict, parsed: dict,
                     sources: dict[str, str],
                     prior_child_id: str | None) -> None:
    """Provenance and falsifiability *admission*, never semantic correctness.

    A self-written rationale alone cannot authorize a material decision.
    The accepted source IDs+hashes must be independently reread from the live
    corpus at admission, audit and Worker execution. The cited facts may STILL
    be semantically irrelevant; only a real outcome evaluation can resolve it.
    """
    basis = candidate["decision_basis"]
    if basis["previous_result_task_id"] != prior_child_id:
        raise ValueError("PREVIOUS_DECISION_RESULT_NOT_GROUNDED")
    # A method with missing actual inputs is ineligible before comparison:
    # citing a ghost file would not make that method executable.
    if not _selected_sources_present(parsed["selected"], sources):
        raise ValueError("SELECTED_NATIVE_SOURCE_UNAVAILABLE")
    if (parsed["alternative"] is not None
        and not _selected_sources_present(parsed["alternative"], sources)):
        raise ValueError("ALTERNATIVE_NATIVE_SOURCE_UNAVAILABLE")
    refs = basis["source_refs"]
    cited = {ref["path"] for ref in refs}
    if any(sources.get(ref["path"]) != ref["sha256"] for ref in refs):
        raise ValueError("DECISION_SOURCE_ID_OR_DIGEST_UNVERIFIABLE")
    required = _method_paths(parsed["selected"], sources)
    if parsed["alternative"] is not None:
        required |= _method_paths(parsed["alternative"], sources)
    if not required.issubset(cited):
        raise ValueError("METHOD_RESEARCH_SOURCES_NOT_CITED")
    if (parsed["selected"]["objective"] == "investigate_evidence"
        and not any(Path(x).suffix.lower() in (".md", ".txt") for x in cited)):
        raise ValueError("INVESTIGATION_SOURCE_NOT_GROUNDED")
    if not refs and not prior_child_id and (
            parsed["selected"]["objective"] != "discover_public_tools"):
        raise ValueError("NO_INDEPENDENT_DECISION_INPUT")



def _native_hypotheses(db: sqlite3.Connection, root_id: str,
                       contract: dict) -> list[dict]:
    """One auditable hypothesis queue for BOTH user and agent-origin ideas.

    Claimed origin is informative, not identity proof or a grant. Sources are
    proposals to CHALLENGE, never executable instructions.
    """
    rows = db.execute(
        "SELECT event_id,details FROM events WHERE task_id=? "
        "AND kind='NATIVE_HYPOTHESIS_RECORDED' ORDER BY event_id",
        (root_id,)).fetchall()
    if len(rows) > _MAX_HYPOTHESES:
        raise ValueError("NATIVE_HYPOTHESIS_BOUND_EXCEEDED")
    result = []
    seen = set()
    for row in rows:
        receipt = json.loads(row["details"])
        if (not isinstance(receipt, dict)
            or set(receipt) != {"idea", "claimed_origin", "proposal_sha256",
                                "contract_sha256", "authorizes_action"}
            or receipt["claimed_origin"] not in ("user", "agent")
            or not isinstance(receipt["idea"], str)
            or not 4 <= len(receipt["idea"].strip()) <= 512
            or receipt["proposal_sha256"] != _digest(receipt["idea"])
            or receipt["contract_sha256"] != _digest(contract)
            or receipt["authorizes_action"] is not False
            or receipt["proposal_sha256"] in seen):
            raise ValueError("NATIVE_HYPOTHESIS_RECEIPT_INVALID")
        seen.add(receipt["proposal_sha256"])
        result.append({"event_id": row["event_id"],
                       "claimed_origin": receipt["claimed_origin"],
                       "idea": receipt["idea"],
                       "proposal_sha256": receipt["proposal_sha256"]})
    return result


def _challenge_hypotheses(candidate: dict, hypotheses: list[dict]) -> None:
    """Check each observed idea was explicitly challenged, NOT its correctness."""
    reviews = candidate.get("hypothesis_reviews")
    if not hypotheses and reviews is None:
        return
    if (not isinstance(reviews, list) or len(reviews) != len(hypotheses)
        or len(reviews) > _MAX_HYPOTHESES):
        raise ValueError("NATIVE_HYPOTHESES_NOT_CHALLENGED")
    covered = set()
    for review in reviews:
        if (not isinstance(review, dict)
            or set(review) != {"proposal_sha256", "disposition",
                               "counterargument", "verification_needed"}
            or review["disposition"] not in _HYPOTHESIS_DISPOSITIONS
            or not isinstance(review["counterargument"], str)
            or not isinstance(review["verification_needed"], str)
            or not 12 <= len(review["counterargument"].strip()) <= 500
            or not 12 <= len(review["verification_needed"].strip()) <= 500
            or not isinstance(review["proposal_sha256"], str)
            or review["proposal_sha256"] in covered):
            raise ValueError("NATIVE_HYPOTHESES_NOT_CHALLENGED")
        covered.add(review["proposal_sha256"])
    if covered != {h["proposal_sha256"] for h in hypotheses}:
        raise ValueError("NATIVE_HYPOTHESES_NOT_CHALLENGED")


def _new_independent_source_cited(
        candidate: dict, original_source_names: list[str],
        admitted_sources: dict[str, str]) -> bool:
    """Detect a real, newly admitted source, NOT semantic resolution.

    The model cannot close its own outstanding research obligation merely by
    changing the review's prose/disposition. The new source must be present in
    the current independently hashed corpus and cited in the proposal.
    Neither a source hash nor a citation establishes that the new information
    actually settles the question; the full owner result remains unverified.
    """
    prior = set(original_source_names)
    return any(
        ref["path"] not in prior
        and admitted_sources.get(ref["path"]) == ref["sha256"]
        for ref in candidate["decision_basis"]["source_refs"])


def record_native_hypothesis(db_path: Path, workspace: Path, fixtures: Path,
                             root_id: str, *, origin: str, idea: str,
                             observation_sha256: str) -> dict:
    """Admit a proposed METHOD IDEA for scrutiny without admitting an action.

    Does not claim to authenticate the human or create owner permissions;
    the existing local caller/grant must already be trusted. Distinguish a
    binding original owner objective from anyone's proposed implementation.
    """
    if (origin not in ("user", "agent")
        or not isinstance(idea, str)
        or not 4 <= len(idea.strip()) <= 512
        or not isinstance(observation_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", observation_sha256)):
        raise ValueError("INVALID_NATIVE_HYPOTHESIS")
    require_initialized_ledger(db_path)
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            observed = _audit(db, db_path, workspace, fixtures, root_id)
            if observed["status"] != "NATIVE_NEXT_DECISION_ADMISSIBLE":
                raise ValueError("NATIVE_DECISION_NOT_ADMISSIBLE:" +
                                 observed["status"])
            if observed["observation_sha256"] != observation_sha256:
                raise ValueError("NATIVE_STALE_OBSERVATION")
            if len(observed["hypotheses"]) >= _MAX_HYPOTHESES:
                raise ValueError("NATIVE_HYPOTHESIS_BOUND_EXCEEDED")
            digest = _digest(idea)
            if any(h["proposal_sha256"] == digest
                   for h in observed["hypotheses"]):
                raise ValueError("DUPLICATE_NATIVE_HYPOTHESIS")
            root = db.execute(
                "SELECT source_spec FROM tasks WHERE task_id=?",
                (root_id,)).fetchone()
            contract = json.loads(root["source_spec"])
            event(db, root_id, "NATIVE_HYPOTHESIS_RECORDED", {
                "idea": idea, "claimed_origin": origin,
                "proposal_sha256": digest,
                "contract_sha256": _digest(contract),
                "authorizes_action": False,
            })
            db.commit()
            return {
                "status": "NATIVE_HYPOTHESIS_RECORDED",
                "root_task_id": root_id, "proposal_sha256": digest,
                "authorizes_action": False,
                "origin_authenticated": False,
                "owner_outcome_verified": False,
            }
        except BaseException:
            db.rollback()
            raise


def register_native_goal(db_path: Path, goal: str, *,
                         allow_public_discovery: bool = False) -> str:
    """Add the original goal without invoking the fixed-grammar open_goal router."""
    contract = _contract(goal, allow_public_discovery=allow_public_discovery)
    require_initialized_ledger(db_path)
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            auth = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if auth is None or auth["write_allowed"] != 1:
                raise PermissionError("NATIVE_GOAL_CURRENT_GRANT_REQUIRED")
            root = create_task(db, contract, commit=False)
            db.execute("UPDATE tasks SET state='DECOMPOSED',"
                       "decision='AWAIT_NATIVE_DECISION',"
                       "state_version=state_version+1 WHERE task_id=?", (root,))
            event(db, root, "NATIVE_GOAL_REGISTERED", {
                "contract_sha256": _digest(contract),
                "owner_outcome_verified": False,
                "external_effect_authorized": False})
            db.commit()
            return root
        except BaseException:
            db.rollback()
            raise


def _registered_native_contract_matches(
        db: sqlite3.Connection, root_id: str, contract: dict) -> bool:
    """Shared original-goal identity check for audits and cold resumption.

    A structurally valid model/ledger record does not prove registration.
    The original event fingerprint independently binds its admitted bytes.
    This read-only check never grants a runnable task or approves an outcome.
    """
    if not _valid_contract(contract):
        return False
    registrations = db.execute(
        "SELECT details FROM events WHERE task_id=? "
        "AND kind='NATIVE_GOAL_REGISTERED'", (root_id,)).fetchall()
    return (len(registrations) == 1
            and json.loads(registrations[0]["details"]) == {
                "contract_sha256": _digest(contract),
                "owner_outcome_verified": False,
                "external_effect_authorized": False,
            })


def _audit(db: sqlite3.Connection, db_path: Path,
           workspace: Path, fixtures: Path, root_id: str) -> dict:
    """Independent lineage and live evidence readback, no task writes."""
    fail = {"root_task_id": root_id, "status": "NATIVE_GOAL_UNVERIFIABLE",
            "owner_outcome_verified": False, "business_outcome_verified": False}
    root = db.execute(
        "SELECT * FROM tasks WHERE task_id=? AND parent_task IS NULL",
        (root_id,)).fetchone()
    if root is None or root["state"] != "DECOMPOSED":
        return {**fail, "reason": "ORIGINAL_GOAL_NOT_ACTIVE"}
    try:
        contract = json.loads(root["source_spec"])
        if not _registered_native_contract_matches(db, root_id, contract):
            raise ValueError("ORIGINAL_RECEIPT_CHANGED")
        hypotheses = _native_hypotheses(db, root_id, contract)
        decisions = db.execute(
            "SELECT event_id,details FROM events WHERE task_id=? "
            "AND kind='NATIVE_DECISION_ADMITTED' "
            "ORDER BY event_id", (root_id,)).fetchall()
        children = db.execute(
            "SELECT * FROM tasks WHERE parent_task=? ORDER BY created_at,task_id",
            (root_id,)).fetchall()
        if len(decisions) > contract["max_decisions"] or len(children) != len(decisions):
            raise ValueError("DECISION_CHILD_CARDINALITY_CHANGED")
        by_id = {row["task_id"]: row for row in children}
        if len(by_id) != len(children):
            raise ValueError("DUPLICATE_DECISION_CHILD")
        current_sources = _sources(fixtures)
        observations = []
        previous_id = None
        previous_decision_event_id = -1
        # Replay the EXISTING immutable decision events to recover unresolved
        # concerns. A review marked UNRESOLVED is not an outcome observation.
        # Do not erase it merely because one decision/Worker tick occurred.
        unresolved_hypotheses: dict[str, dict] = {}
        for index, item in enumerate(decisions):
            receipt = json.loads(item["details"])
            if (not isinstance(receipt, dict)
                or set(receipt) != {"child_task_id", "ordinal", "proposal",
                                   "selected_plan_sha256", "source_sha256",
                                   "prior_child_task_id", "owner_outcome_verified"}
                or receipt["ordinal"] != index
                or receipt["prior_child_task_id"] != previous_id
                or receipt["owner_outcome_verified"] is not False):
                raise ValueError("DECISION_RECEIPT_CHANGED")
            parsed = _proposal(receipt["proposal"], contract)
            newly_recorded = [
                h for h in hypotheses if (previous_decision_event_id <
                    h["event_id"] < item["event_id"])]
            reviews = receipt["proposal"].get("hypothesis_reviews") or []
            reviewed_hashes = {
                review.get("proposal_sha256") for review in reviews
                if isinstance(review, dict)}
            # Historical admitted receipts were only required to review NEW
            # hypotheses. Reconstruct unresolved legacy concerns even when
            # an old receipt omitted them; never reinterpret omission as a
            # verified resolution or invalidate unrelated legitimate work.
            carried_and_reviewed = [
                h for digest, h in unresolved_hypotheses.items()
                if digest in reviewed_hashes]
            _challenge_hypotheses(
                receipt["proposal"], newly_recorded + carried_and_reviewed)
            candidates = {
                h["proposal_sha256"]: h
                for h in newly_recorded + carried_and_reviewed}
            for review in reviews:
                digest = review["proposal_sha256"]
                if review["disposition"] == "UNRESOLVED_RESEARCH_REQUIRED":
                    if digest not in unresolved_hypotheses:
                        # The first unresolved review establishes provenance,
                        # but not the evidence baseline for every future review.
                        unresolved_hypotheses[digest] = {
                            **candidates[digest],
                            "unresolved_source_names": sorted(
                                receipt["source_sha256"]),
                        }
                # On EVERY subsequent review, advance the last-examined
                # source inventory, even for model-relabelled dispositions.
                # A cited source is fresh only once. Replay uses the original
                # admission receipt, never the current file list or model
                # recollection; a changed source remains separately blocked.
                if digest in unresolved_hypotheses:
                    unresolved_hypotheses[digest]["last_review_source_names"] = (
                        sorted(receipt["source_sha256"]))
                # An external domain/outcome oracle would need a distinct
                # proof-bearing resolution receipt. This ledger has none;
                # model prose and added files do NOT close an old question.
            previous_decision_event_id = item["event_id"]
            selected = parsed["selected"]
            child = by_id.get(receipt["child_task_id"])
            if (child is None or child["goal_rev"] != root["goal_rev"]
                or child["grant_rev"] != root["grant_rev"]
                or json.loads(child["source_spec"]) != selected["child_source_spec"]
                or receipt["selected_plan_sha256"] != selected["plan_sha256"]):
                raise ValueError("DECISION_CHILD_PROVENANCE_CHANGED")
            if not _sources_compatible(
                    receipt["source_sha256"], current_sources,
                    selected["child_source_spec"]["kind"],
                    finished=child["state"] in ("NEEDS_REVIEW", "VERIFIED")):
                return {**fail, "status": "NATIVE_SOURCE_CHANGED",
                        "original_goal": contract["goal"],
                        "reason": "SOURCE_PIN_DRIFT"}
            _ground_decision(
                receipt["proposal"], parsed, receipt["source_sha256"], previous_id)
            previous_id = child["task_id"]
            verdict = "NOT_YET_INDEPENDENTLY_CHECKED"
            if child["state"] in ("NEEDS_REVIEW", "VERIFIED"):
                kind = selected["child_source_spec"]["kind"]
                if kind == "goal_case":
                    from .goal_audit import audit_goal
                    result = audit_goal(db_path, workspace, fixtures, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "CANDIDATE_MECHANICALLY_VALID"
                elif kind == "record_reconciliation":
                    from .reconciliation_oracle import audit_stored_report
                    result = audit_stored_report(
                        db_path, workspace, fixtures, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "REPORT_MECHANICALLY_VERIFIED"
                elif kind == "investigate_goal":
                    from .investigation import audit_investigation
                    result = audit_investigation(
                        db_path, workspace, fixtures, child["task_id"],
                        original_scope_names=frozenset(receipt["source_sha256"]))
                    verdict = result["status"]
                    accepted = verdict == "SOURCE_GROUNDED_UNREVIEWED"
                elif kind == "public_tool_discovery":
                    from .public_tool_discovery import audit_public_discovery
                    result = audit_public_discovery(
                        db_path, workspace, child["task_id"])
                    verdict = result["status"]
                    accepted = verdict == "PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED"
                else:
                    accepted = False
                if not accepted:
                    return {**fail, "status": "NATIVE_EVIDENCE_UNVERIFIABLE",
                            "original_goal": contract["goal"],
                            "reason": verdict}
            observations.append({
                "task_id": child["task_id"], "task_state": child["state"],
                "selected_objective": selected["objective"],
                "alternative_objective": (parsed["alternative"]["objective"]
                                         if parsed["alternative"] is not None else None),
                "mechanical_verdict": verdict,
                "error_code": child["error_code"],
                # Replay the previously recorded comparative RESEARCH, not
                # just method names. On cold resume an external cognitive
                # client needs the falsifier, rejected alternative and
                # still-unverified explanations to challenge/revise a method.
                # These are original, untrusted proposals already stored in
                # this ledger; neither hashes nor prose prove semantic truth.
                "research_trace": {
                    "selected_reason": receipt["proposal"]["decision_reason"],
                    "alternative_reason": receipt["proposal"]["alternative_reason"],
                    "expected_evidence": receipt["proposal"]["expected_evidence"],
                    "challenge": receipt["proposal"]["decision_basis"]["challenge"],
                    "falsifier": receipt["proposal"]["decision_basis"]["falsifier"],
                    "uncertainty": receipt["proposal"]["decision_basis"]["uncertainty"],
                    "source_refs": receipt["proposal"]["decision_basis"]["source_refs"],
                    "hypothesis_reviews": (
                        receipt["proposal"].get("hypothesis_reviews") or []),
                    "semantic_verdict": "UNVERIFIED_MODEL_ARGUMENTS",
                },
                "owner_outcome_verified": False})
        auth = db.execute(
            "SELECT * FROM authority WHERE singleton=1").fetchone()
        grant_current = bool(auth and auth["write_allowed"] == 1
            and (auth["goal_rev"], auth["grant_rev"]) ==
                (root["goal_rev"], root["grant_rev"]))
        # Hash SOURCE IDs and externally observed task states/results, not
        # private goal text in public event logs.
        fingerprint = _digest({
            "root": root_id, "contract": _digest(contract),
            "goal_rev": root["goal_rev"], "grant_rev": root["grant_rev"],
            "grant_current": grant_current, "sources": current_sources,
            "decisions": [json.loads(e["details"]) for e in decisions],
            "hypotheses": hypotheses,
            "children": observations})
        waiting = bool(observations and
            observations[-1]["task_state"] in ("PENDING", "RUNNING"))
        return {
            "root_task_id": root_id,
            "status": ("NATIVE_GRANT_REVOKED" if not grant_current
                       else "NATIVE_AWAITING_WORKER" if waiting
                       else "NATIVE_DECISION_BUDGET_EXHAUSTED"
                            if len(decisions) >= contract["max_decisions"]
                       else "NATIVE_NEXT_DECISION_ADMISSIBLE"),
            "original_goal": contract["goal"],
            "observation_sha256": fingerprint,
            "decisions": observations, "decision_count": len(decisions),
            "hypotheses": hypotheses,
            "pending_hypotheses": (
                list(unresolved_hypotheses.values())
                + [h for h in hypotheses
                   if h["event_id"] > previous_decision_event_id]),
            "owner_outcome_verified": False, "business_outcome_verified": False,
        }
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error,
            IntentError, SourceUnavailable, PermissionError) as exc:
        return {**fail, "reason": type(exc).__name__}


def inspect_native_goal(db_path: Path, workspace: Path, fixtures: Path,
                        root_id: str) -> dict:
    """Read-only resumable native-cognition decision state."""
    if (not isinstance(root_id, str) or not _ID.fullmatch(root_id)
        or not db_path.is_file() or db_path.is_symlink()):
        return {"root_task_id": root_id, "status": "NATIVE_GOAL_UNVERIFIABLE",
                "owner_outcome_verified": False}
    uri = db_path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        return _audit(db, db_path, workspace, fixtures, root_id)


def admit_native_decision(db_path: Path, workspace: Path, fixtures: Path,
                          root_id: str, candidate: dict) -> dict:
    """Append ONE model proposal if current evidence CAS still matches.

    The original Host/Worker executes the child on its next tick. This function
    has no tool runner, daemon, model API, independent scheduler or new grant.
    """
    require_initialized_ledger(db_path)
    if not isinstance(root_id, str) or not _ID.fullmatch(root_id):
        raise ValueError("INVALID_NATIVE_ROOT_ID")
    with closing(connect(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            observed = _audit(db, db_path, workspace, fixtures, root_id)
            if observed["status"] != "NATIVE_NEXT_DECISION_ADMISSIBLE":
                raise ValueError("NATIVE_DECISION_NOT_ADMISSIBLE:" + observed["status"])
            # A still-admissible task budget does NOT grant permission to
            # keep acting after an independent whole-original LOCAL outcome
            # has already been proven. This central admission check is inside
            # the same SQLite BEGIN IMMEDIATE path as other decision grants.
            from .owner_postcondition import inspect_owner_local_outcome
            owner_outcome = inspect_owner_local_outcome(
                db_path, workspace, fixtures, root_id)
            if owner_outcome["local_owner_outcome_verified"]:
                raise ValueError("NATIVE_ORIGINAL_OWNER_ALREADY_VERIFIED")
            root = db.execute("SELECT * FROM tasks WHERE task_id=?",
                              (root_id,)).fetchone()
            contract = json.loads(root["source_spec"])
            parsed = _proposal(candidate, contract)
            if candidate["observation_sha256"] != observed["observation_sha256"]:
                raise ValueError("NATIVE_STALE_OBSERVATION")
            _challenge_hypotheses(candidate, observed["pending_hypotheses"])
            # Compare/grant and exact source snapshot rechecked *inside*
            # the original SQLite write transaction.
            auth = db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if (auth is None or auth["write_allowed"] != 1
                or (auth["goal_rev"], auth["grant_rev"]) !=
                   (root["goal_rev"], root["grant_rev"])):
                raise PermissionError("CURRENT_NATIVE_GRANT_REVOKED")
            source_hashes = _sources(fixtures)
            _ground_decision(
                candidate, parsed, source_hashes,
                observed["decisions"][-1]["task_id"] if observed["decisions"] else None)
            # Reuse one state/evidence boundary for every registered method.
            # A verified child task result alone does not refute an unrelated
            # question about source completeness. A model can keep it OPEN,
            # but cannot re-label it closed without a newly added, re-read,
            # cited source. This only admits re-evaluation, never truth.
            # Freshness is compared to the LAST review, not the first one.
            reviews = {
                x["proposal_sha256"]: x
                for x in candidate.get("hypothesis_reviews", [])}
            for hypothesis in observed["pending_hypotheses"]:
                last_reviewed_sources = hypothesis.get("last_review_source_names")
                if last_reviewed_sources is None:
                    continue  # Newly recorded, not previously unresolved.
                review = reviews[hypothesis["proposal_sha256"]]
                if (review["disposition"] != "UNRESOLVED_RESEARCH_REQUIRED"
                    and not _new_independent_source_cited(
                        candidate, last_reviewed_sources, source_hashes)):
                    raise ValueError("UNRESOLVED_HYPOTHESIS_NO_NEW_EVIDENCE")
            # A proposal can be syntactically executable yet contradict an
            # UNAMBIGUOUS original local acceptance contract: reversed CSV
            # roles or unrelated CSV work for an explicitly named JSON draft.
            # Reject BEFORE creating a child, without claiming general
            # semantic competence for unknown or compound owner language.
            # This reuses the SAME parsing contract as the independent owner
            # postcondition instead of a competing keyword router.
            from .owner_postcondition import (
                _explicit_owner_local_contract, _full_owner_scope_is_supported)
            if (_explicit_owner_local_contract(contract["goal"]) is not None
                and not _full_owner_scope_is_supported(
                    contract["goal"], parsed["selected"])):
                raise ValueError("NATIVE_METHOD_CONTRADICTS_EXPLICIT_OWNER_CONTRACT")
            previous_receipts = db.execute(
                "SELECT details FROM events WHERE task_id=? "
                "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
                (root_id,)).fetchall()
            last_feedback = (observed["decisions"][-1]
                             if observed["decisions"] else None)
            for receipt_row in previous_receipts:
                previous_receipt = json.loads(receipt_row["details"])
                prior_plan = _proposal(previous_receipt["proposal"], contract)["selected"]
                if prior_plan["objective"] != parsed["selected"]["objective"]:
                    continue
                added = set(source_hashes) - set(previous_receipt["source_sha256"])
                selected_plan_changed = (
                    previous_receipt["selected_plan_sha256"] !=
                    parsed["selected"]["plan_sha256"])
                cited = {item["path"] for item in
                         candidate["decision_basis"]["source_refs"]}
                # A verified failure IS new result evidence. Correcting the
                # immediately failed registered method need not fabricate a new
                # source file; it must actually change the typed plan and the
                # Worker still checks earlier task lineage and current grant.
                # A successful prior method never permits a no-evidence rerun.
                failed_method_feedback = bool(
                    last_feedback
                    and previous_receipt["child_task_id"] == last_feedback["task_id"]
                    and last_feedback["selected_objective"] ==
                        parsed["selected"]["objective"]
                    and last_feedback["task_state"] == "UNKNOWN"
                    and last_feedback["error_code"] in (
                        "NO_SAFE_GOAL_PLAN", "JOIN_KEY_AMBIGUOUS"))
                # Mechanical artifact validity is NOT an owner success.
                # An independently recognizable complete owner postcondition
                # may expose reversed named inputs even when both CSV reads
                # and the generated discrepancy report were mechanically valid.
                # Permit exactly a changed typed plan whose newly pinned
                # inputs match the COMPLETE original owner wording. This is
                # not a model-declared failure, source rewrite, new authority,
                # or permission to repeat an already owner-correct method.
                corrected_owner_binding = False
                if (last_feedback
                    and previous_receipt["child_task_id"] ==
                        last_feedback["task_id"]
                    and last_feedback["task_state"] == "NEEDS_REVIEW"
                    and last_feedback["mechanical_verdict"] ==
                        "REPORT_MECHANICALLY_VERIFIED"
                    and parsed["selected"]["objective"] == "compare_records"):
                    from .owner_postcondition import _full_owner_scope_is_supported
                    corrected_owner_binding = (
                        _full_owner_scope_is_supported(
                            contract["goal"], parsed["selected"])
                        and not _full_owner_scope_is_supported(
                            contract["goal"], prior_plan))
                if not (selected_plan_changed and (
                        (added and (added & cited)) or failed_method_feedback
                        or corrected_owner_binding)):
                    raise ValueError("REPEATED_NATIVE_METHOD_WITHOUT_NEW_EVIDENCE")
            # Tool eligibility is not semantic goal relevance. A model must
            # challenge its selected method and cite live evidence, but must
            # not fabricate an irrelevant competitor merely because a JSON
            # and CSV tool both happen to find compatible local file types.
            # An omitted alternative remains an untrusted model judgment,
            # never independent proof that the method matches owner intent.
            if not _selected_sources_present(parsed["selected"], source_hashes):
                raise ValueError("SELECTED_NATIVE_SOURCE_UNAVAILABLE")
            child = create_task(db, parsed["selected"]["child_source_spec"],
                                parent=root_id, commit=False)
            previous = (observed["decisions"][-1]["task_id"]
                        if observed["decisions"] else None)
            event(db, root_id, "NATIVE_DECISION_ADMITTED", {
                "child_task_id": child,
                "ordinal": observed["decision_count"],
                "proposal": candidate,
                "selected_plan_sha256": parsed["selected"]["plan_sha256"],
                "source_sha256": source_hashes,
                "prior_child_task_id": previous,
                "owner_outcome_verified": False})
            db.commit()
            return {"status": "NATIVE_METHOD_ENQUEUED",
                    "root_task_id": root_id, "child_task_id": child,
                    "selected_objective": parsed["selected"]["objective"],
                    "alternative_objective": (parsed["alternative"]["objective"]
                                              if parsed["alternative"] is not None else None),
                    "business_outcome_verified": False,
                    "owner_outcome_verified": False}
        except BaseException:
            db.rollback()
            raise


def native_child_admitted(db: sqlite3.Connection, fixtures: Path,
                          task_id: str, *,
                          workspace: Path | None = None,
                          db_path: Path | None = None) -> bool:
    """Worker provenance check; refuse forged model-selected child or drift.

    Full artifact/outcome audit is performed by the independent Host readback.
    """
    try:
        task = db.execute("SELECT * FROM tasks WHERE task_id=?",
                          (task_id,)).fetchone()
        root = db.execute("SELECT * FROM tasks WHERE task_id=?",
                          (task["parent_task"],)).fetchone()
        contract = json.loads(root["source_spec"])
        if (root["state"] != "DECOMPOSED"
            or not _valid_contract(contract)):
            return False
        receipts = db.execute(
            "SELECT event_id,details FROM events WHERE task_id=? "
            "AND kind='NATIVE_DECISION_ADMITTED' ORDER BY event_id",
            (root["task_id"],)).fetchall()
        children = db.execute("SELECT task_id FROM tasks WHERE parent_task=?",
                              (root["task_id"],)).fetchall()
        if (not 1 <= len(receipts) <= contract["max_decisions"]
            or len(children) != len(receipts)):
            return False
        pinned = _sources(fixtures)
        hypotheses = _native_hypotheses(db, root["task_id"], contract)
        known = set()
        previous = None
        previous_decision_event_id = -1
        for ordinal, r in enumerate(receipts):
            entry = json.loads(r["details"])
            if (entry["ordinal"] != ordinal
                or entry["prior_child_task_id"] != previous
                or entry["owner_outcome_verified"] is not False):
                return False
            parsed = _proposal(entry["proposal"], contract)
            _challenge_hypotheses(
                entry["proposal"], [h for h in hypotheses
                    if previous_decision_event_id < h["event_id"] < r["event_id"]])
            previous_decision_event_id = r["event_id"]
            selected = parsed["selected"]
            candidate = db.execute(
                "SELECT source_spec,goal_rev,grant_rev,state "
                "FROM tasks WHERE task_id=?", (entry["child_task_id"],)).fetchone()
            if candidate is None or not _sources_compatible(
                    entry["source_sha256"], pinned,
                    selected["child_source_spec"]["kind"],
                    finished=candidate["state"] in ("NEEDS_REVIEW", "VERIFIED")):
                return False
            _ground_decision(
                entry["proposal"], parsed, entry["source_sha256"], previous)
            if (candidate is None
                or json.loads(candidate["source_spec"]) != selected["child_source_spec"]
                or entry["selected_plan_sha256"] != selected["plan_sha256"]
                or (candidate["goal_rev"], candidate["grant_rev"]) !=
                   (root["goal_rev"], root["grant_rev"])
                or entry["child_task_id"] in known):
                return False
            known.add(entry["child_task_id"])
            previous = entry["child_task_id"]
        if known != {x["task_id"] for x in children} or task_id not in known:
            return False
        if workspace is not None and db_path is not None:
            # The Worker must independently revisit live previous artifacts
            # AFTER the candidate was admitted. A successful earlier receipt
            # must not release an unrelated successor after source/artifact
            # tampering, revocation or mechanical invalidation.
            checked = _audit(db, db_path, workspace, fixtures, root["task_id"])
            if checked["status"] not in (
                "NATIVE_AWAITING_WORKER",
                "NATIVE_NEXT_DECISION_ADMISSIBLE",
                "NATIVE_DECISION_BUDGET_EXHAUSTED"):
                return False
            observations = checked["decisions"]
            index = next((i for i, x in enumerate(observations)
                          if x["task_id"] == task_id), -1)
            if index < 0:
                return False
            for previous in observations[:index]:
                if previous["task_state"] in ("NEEDS_REVIEW", "VERIFIED"):
                    if previous["mechanical_verdict"] not in (
                        "CANDIDATE_MECHANICALLY_VALID",
                        "REPORT_MECHANICALLY_VERIFIED",
                        "SOURCE_GROUNDED_UNREVIEWED",
                        "PUBLIC_TOOL_LEADS_MECHANICALLY_GROUNDED"):
                        return False
                elif (previous["task_state"] == "UNKNOWN"
                      and previous["error_code"] in (
                        "NO_SAFE_GOAL_PLAN", "JOIN_KEY_AMBIGUOUS")):
                    # A known bounded local-method failure may justify a
                    # different local experiment, not an owner success.
                    continue
                else:
                    return False
        return True
    except (KeyError, ValueError, TypeError, sqlite3.Error, OSError,
            SourceUnavailable, IntentError, PermissionError):
        return False
