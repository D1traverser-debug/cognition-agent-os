"""P9: typed, bounded intent compiler over existing capability contracts.

Goals are data, never commands. The compiler decomposes broad typed outcomes
into an evidence source, alternatives, action and acceptance steps, and maps
them to already-registered guarded task families. It does NOT claim open-ended
natural-language comprehension or unconstrained tool discovery.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .goal_loop import validate_goal, GoalError
from .reconciliation import validate_reconciliation, ReconciliationError
from .investigation import validate_investigation, InvestigationInvalid
from .public_tool_discovery import validate_public_discovery, PublicDiscoveryInvalid

MAX_INTENT_BYTES=16384
MAX_STEPS=5
SUPPORTED_INTENTS={"ensure_structure","compare_records","investigate_evidence","discover_public_tools"}
ALLOWED_ROLES={
    "ensure_structure":("input",),
    "compare_records":("reference","observed"),
    "investigate_evidence":(),
    "discover_public_tools":(),
}


class IntentError(ValueError):
    pass


def _resources(items: object, objective: str) -> dict[str,str]:
    roles=ALLOWED_ROLES[objective]
    if not isinstance(items,list) or len(items)!=len(roles):
        raise IntentError("Wrong number of source resources")
    result={}
    for item in items:
        if (not isinstance(item,dict) or set(item)!={"role","path"}
                or not isinstance(item["role"],str)
                or item["role"] not in roles or item["role"] in result):
            raise IntentError("Unexpected resource role or duplicate")
        value=item["path"]
        if (not isinstance(value,str) or not 1<=len(value)<=200
                or Path(value).is_absolute() or value in (".","..")
                or "/" in value or "\\" in value or ".." in Path(value).parts
                or ":" in value):
            raise IntentError("Unsafe input scope")
        result[item["role"]]=value
    if set(result)!=set(roles) or len(set(result.values()))!=len(roles):
        raise IntentError("Incomplete or shared resource bindings")
    return result


def compile_intent(intent: dict) -> dict:
    if not isinstance(intent,dict) or intent.get("kind")!="goal_intent":
        raise IntentError("Not a typed goal_intent")
    try:
        raw=json.dumps(intent,ensure_ascii=False,sort_keys=True)
    except (ValueError,TypeError) as exc:
        raise IntentError("Unserializable intent") from exc
    if len(raw.encode("utf-8"))>MAX_INTENT_BYTES:
        raise IntentError("Intent budget exceeded")
    objective=intent.get("objective")
    if not isinstance(objective,str) or objective not in SUPPORTED_INTENTS:
        raise IntentError("No registered capability for objective")
    source=_resources(intent.get("resources"),objective)
    if objective=="ensure_structure":
        if set(intent)!={"kind","objective","resources","requirements"}:
            raise IntentError("Unexpected requirements or authority claims")
        reqs=intent["requirements"]
        if not isinstance(reqs,list) or not 1<=len(reqs)<=16:
            raise IntentError("Invalid acceptance constraint set")
        result={}
        for rule in reqs:
            if (not isinstance(rule,dict) or set(rule)!={"field","equals"}
                    or not isinstance(rule["field"],str) or rule["field"] in result):
                raise IntentError("Malformed/duplicate acceptance constraint")
            result[rule["field"]]=rule["equals"]
        try:
            spec=validate_goal({"kind":"goal_case","goal_type":"json_keys",
                                "input":source["input"],"desired":result})
        except (GoalError,TypeError,ValueError) as exc:
            raise IntentError("Structural objective constraints invalid") from exc
        capability="json_structural_conformance_v1"
        expected="JSON_REQUIRED_FIELDS_PRESERVED"
    elif objective=="compare_records":
        if set(intent) not in ({"kind","objective","resources"},
                               {"kind","objective","resources","relationship_contract"}):
            raise IntentError("Unknown relationship or contract extension")
        record_spec={
            "kind":"record_reconciliation","reference":source["reference"],
            "observed":source["observed"],"objective":"identify_discrepancies"}
        if "relationship_contract" in intent:
            record_spec["relationship_contract"]=intent["relationship_contract"]
        try:
            spec=validate_reconciliation(record_spec)
        except (ReconciliationError,TypeError,ValueError) as exc:
            raise IntentError("Comparison objective scope invalid") from exc
        capability="csv_evidence_reconciliation_v1"
        expected="SQLITE_RECOMPUTED_REPORT_OR_ABSTENTION"
    elif objective=="investigate_evidence":
        if set(intent)!={"kind","objective","resources","question"}:
            raise IntentError("Research objective requires bounded original question")
        try:
            spec=validate_investigation({"kind":"investigate_goal",
                "question":intent["question"],"scope":"LOCAL_EVIDENCE_ONLY"})
        except (InvestigationInvalid,ValueError,TypeError) as exc:
            raise IntentError("Invalid local research objective") from exc
        capability="source_quote_grounded_investigation_v1"
        expected="SOURCE_GROUNDED_UNREVIEWED_OR_ABSTAINED"
    else:
        if set(intent)!={"kind","objective","resources","terms"}:
            raise IntentError("Explicit public tool-search scope required")
        try:
            spec=validate_public_discovery({
                "kind":"public_tool_discovery",
                "scope":"GITHUB_PUBLIC_METADATA_ONLY",
                "terms":intent["terms"]})
        except (PublicDiscoveryInvalid,ValueError,TypeError) as exc:
            raise IntentError("Invalid public metadata discovery contract") from exc
        capability="public_github_tool_leads_v1"
        expected="PUBLIC_CANDIDATES_REQUIRE_INDEPENDENT_REVIEW"
    steps=[
        {"stage":"OBSERVE","capability":"local_evidence_read","resources":source},
        {"stage":"CHALLENGE","capability":"bounded_hypotheses","family":capability},
        {"stage":"PLAN","capability":"registered_family_planner","family":capability},
        {"stage":"CHECK","capability":"separate_mechanical_oracle","acceptance":expected},
        {"stage":"COMMIT","capability":"existing_ledger_and_immutable_artifact",
         "source_mutation_allowed":False}
    ]
    if len(steps)>MAX_STEPS:
        raise IntentError("Plan step budget exceeded")
    plan={
        "schema_version":1,"objective":objective,"capability":capability,
        "allowed_effects":"SQLITE_STATE_AND_LOCAL_PROPOSAL_ONLY",
        "steps":steps,"child_source_spec":spec,
        "semantic_domain_approval":False
    }
    plan["plan_sha256"]=hashlib.sha256(
        json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    return plan
