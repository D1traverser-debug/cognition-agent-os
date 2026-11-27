"""P9: typed, bounded intent compiler over existing capability contracts.

Goals are data, never commands. The compiler decomposes broad typed outcomes
into an evidence source, alternatives, action and acceptance steps, and maps
them to already-registered guarded task families. It does NOT claim open-ended
natural-language comprehension or unconstrained tool discovery.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


MAX_INTENT_BYTES=16384
MAX_STEPS=5


class IntentError(ValueError):
    pass


@dataclass(frozen=True)
class NativeCapability:
    """Trusted local method contract. Describes availability, never authority."""
    objective: str
    task_kind: str
    roles: tuple[str, ...]
    source_suffixes: tuple[str, ...]
    minimum_sources: int
    capability_id: str
    acceptance: str
    compile_spec: Callable[[dict, dict[str, str]], dict]
    requires_public_discovery: bool = False
    corpus_wide: bool = False

    def eligible_sources(self, names) -> list[str]:
        return sorted(name for name in names
                      if Path(name).suffix.lower() in self.source_suffixes)

    def eligible(self, names, *, allow_public_discovery: bool) -> bool:
        if self.requires_public_discovery:
            return bool(allow_public_discovery)
        return len(self.eligible_sources(names)) >= self.minimum_sources

    def bound_paths(self, spec: Mapping) -> set[str]:
        return {spec[role] for role in self.roles}

    def sources_present(self, spec: Mapping, names) -> bool:
        # Named sources are already pinned/validated by admission. Preserve
        # prior behavior: catalog suffix hints do not create a new effect gate.
        if self.roles:
            return self.bound_paths(spec).issubset(names)
        if self.corpus_wide:
            return len(self.eligible_sources(names)) >= self.minimum_sources
        return self.requires_public_discovery


def _compile_structure(intent: dict, source: dict[str, str]) -> dict:
    from .goal_loop import validate_goal, GoalError
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
    return spec


def _compile_comparison(intent: dict, source: dict[str, str]) -> dict:
    from .reconciliation import validate_reconciliation, ReconciliationError
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
    return spec


def _compile_investigation(intent: dict, source: dict[str, str]) -> dict:
    from .investigation import validate_investigation, InvestigationInvalid
    if set(intent)!={"kind","objective","resources","question"}:
        raise IntentError("Research objective requires bounded original question")
    try:
        spec=validate_investigation({"kind":"investigate_goal",
            "question":intent["question"],"scope":"LOCAL_EVIDENCE_ONLY"})
    except (InvestigationInvalid,ValueError,TypeError) as exc:
        raise IntentError("Invalid local research objective") from exc
    return spec


def _compile_public_discovery(intent: dict, source: dict[str, str]) -> dict:
    from .public_tool_discovery import validate_public_discovery, PublicDiscoveryInvalid
    if set(intent)!={"kind","objective","resources","terms"}:
        raise IntentError("Explicit public tool-search scope required")
    try:
        spec=validate_public_discovery({
            "kind":"public_tool_discovery",
            "scope":"GITHUB_PUBLIC_METADATA_ONLY",
            "terms":intent["terms"]})
    except (PublicDiscoveryInvalid,ValueError,TypeError) as exc:
        raise IntentError("Invalid public metadata discovery contract") from exc
    return spec


# A single source of native method identity, compiler, source affordance and
# mechanical acceptance. Adding a method is a reviewed code change, not a
# model-supplied plugin import. Runtime dispatch has its separate trusted
# executor binding; catalog checks that the two agree.
_METHODS = (
    NativeCapability("ensure_structure", "goal_case", ("input",),
                     (".json",), 1, "json_structural_conformance_v1",
                     "JSON_REQUIRED_FIELDS_PRESERVED", _compile_structure),
    NativeCapability("compare_records", "record_reconciliation",
                     ("reference", "observed"), (".csv",), 2,
                     "csv_evidence_reconciliation_v1",
                     "SQLITE_RECOMPUTED_REPORT_OR_ABSTENTION", _compile_comparison),
    NativeCapability("investigate_evidence", "investigate_goal", (),
                     (".md", ".txt"), 1, "source_quote_grounded_investigation_v1",
                     "SOURCE_GROUNDED_UNREVIEWED_OR_ABSTAINED",
                     _compile_investigation, corpus_wide=True),
    NativeCapability("discover_public_tools", "public_tool_discovery", (),
                     (), 0, "public_github_tool_leads_v1",
                     "PUBLIC_CANDIDATES_REQUIRE_INDEPENDENT_REVIEW",
                     _compile_public_discovery, requires_public_discovery=True),
)
NATIVE_CAPABILITIES = MappingProxyType({method.objective: method for method in _METHODS})
CAPABILITIES_BY_KIND = MappingProxyType({method.task_kind: method for method in _METHODS})
if len(NATIVE_CAPABILITIES) != len(_METHODS) or len(CAPABILITIES_BY_KIND) != len(_METHODS):
    raise RuntimeError("DUPLICATE_NATIVE_CAPABILITY_ID")
# Stable public names for existing clients; no independently mutable copies.
SUPPORTED_INTENTS = frozenset(NATIVE_CAPABILITIES)
ALLOWED_ROLES = MappingProxyType({key: method.roles for key, method in NATIVE_CAPABILITIES.items()})


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
    method = NATIVE_CAPABILITIES[objective]
    spec = method.compile_spec(intent, source)
    if spec.get("kind") != method.task_kind:
        raise IntentError("Registered capability returned a mismatched task kind")
    capability = method.capability_id
    expected = method.acceptance
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
