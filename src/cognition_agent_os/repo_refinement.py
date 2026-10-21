"""P13: public-evidence-driven local-model revision of a whole-file patch.

An explicitly requested action executes untrusted candidates ONLY inside
the existing offline Docker lab. A bounded already-installed loopback
model sees PUBLIC failed examples but never gold/holdout. On public pass,
freeze one reviewed child in the original task ledger. A model cannot
declare acceptance, promote source or authorize its own run.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .container_lab import candidate_changes,cases_from_bytes,run_suite,ContainerUnavailable
from .repo_repair import audit_repo,_sources,_candidate_from_model,sha
from .source import safe_fixture
from .runner import store_once,ArtifactConflict
from .ledger import connect,create_task,event

MAX_ATTEMPTS_PER_LINEAGE=3
TASK=re.compile(r"[0-9a-f]{32}\Z")


def _deny(status,**fields):
    return {"status":status,"production_write_authorized":False,
            "holdout_seen_by_proposer":False,**fields}


def _public_feedback(changes,public,outcome):
    errors=[]
    for index,(case,observation) in enumerate(zip(public,outcome["observed"])):
        if not observation["pass"]:
            entry={"index":index,
                   "input":case["input"],
                   "expected":case["expected"],
                   "observed_output_sha256":observation["output_sha256"]}
            if observation.get("execution_error") in (
                "CANDIDATE_NONZERO","CANDIDATE_EMPTY_OR_OVERSIZE_OUTPUT",
                "CANDIDATE_INVALID_JSON_OUTPUT"):
                entry["execution_error"]=observation["execution_error"]
            # Actual returned JSON is a useful counterexample. Only
            # PUBLIC run_suite(include_observed=True) can populate it;
            # independent hidden-case calls always use the default False.
            if "observed_value" in observation:
                value=observation["observed_value"]
                if len(json.dumps(value,sort_keys=True).encode())<=512:
                    entry["observed_value"]=value
            errors.append(entry)
    # Public-only feedback; the previously proposed source was untrusted,
    # never verified; model text is data, not an instruction for tools.
    return {"previous_changes":{k:v.decode("utf-8") for k,v in changes.items()},
            "failed_public_cases":errors,"public_total":outcome["total"],
            "public_passes":outcome["passes"]}


def _record_attempt(db_path,tid,expected_task,entry):
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        task=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        auth=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if (not task or not auth or task["state"]!="NEEDS_REVIEW"
            or task["state_version"]!=expected_task["state_version"]
            or task["artifact_hash"]!=expected_task["artifact_hash"]
            or not auth["write_allowed"]
            or auth["goal_rev"]!=task["goal_rev"]
            or auth["grant_rev"]!=task["grant_rev"]):
            db.commit()
            return False
        used=db.execute("""SELECT COUNT(*) FROM events WHERE task_id=?
             AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",(tid,)).fetchone()[0]
        if used>=MAX_ATTEMPTS_PER_LINEAGE:
            db.commit();return False
        event(db,tid,"REPO_LOCAL_PUBLIC_REVISION_TRIAL",entry)
        db.commit()
        return True
    except BaseException:
        db.rollback();raise
    finally:db.close()


def refine_repo_public(db_path:Path,workspace:Path,fixtures:Path,tid:str,
                       *,model:str,max_attempts:int=2)->dict:
    """User invokes intentionally; never automatically from host-tick.

    The caller explicitly authorizes experimental Docker execution and
    non-metered locally installed model queries. No cloud or auto-pull.
    """
    if (not isinstance(tid,str) or not TASK.fullmatch(tid)
        or type(max_attempts) is not int
        or not 1<=max_attempts<=MAX_ATTEMPTS_PER_LINEAGE):
        return _deny("INVALID_PUBLIC_REFINEMENT_REQUEST")
    from .conformance import effect_preflight,capability_disabled,REPAIR_LAB_CAPABILITY
    if capability_disabled(db_path) or capability_disabled(db_path,REPAIR_LAB_CAPABILITY):
        return _deny("CAPABILITY_DISABLED")
    # Verify exact immutable original proposal, task, and public source
    # identities before any candidate is executed or passed to a model.
    audit=audit_repo(db_path,workspace,fixtures,tid)
    if audit["status"]!="REPO_BYTES_MECHANICALLY_VALID":
        return _deny("PARENT_EVIDENCE_UNVERIFIABLE",reason=audit.get("reason"))
    admit=effect_preflight(db_path,workspace,fixtures)
    if not admit["admitted"]:
        return _deny("PREFLIGHT_BLOCKED")
    try:
        uri=db_path.resolve(strict=True).as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row
            task=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
            auth=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            old_trials=db.execute("""SELECT details FROM events WHERE task_id=?
                 AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",(tid,)).fetchall()
            prior=len(old_trials)
            previously_tested=set()
            for old in old_trials:
                evidence=json.loads(old["details"])
                if isinstance(evidence.get("candidate_fingerprint"),str):
                    previously_tested.add(evidence["candidate_fingerprint"])
            if (not task or not auth or task["state"]!="NEEDS_REVIEW"
                or not auth["write_allowed"] or auth["goal_rev"]!=task["goal_rev"]
                or auth["grant_rev"]!=task["grant_rev"]):
                return _deny("REVISION_AUTHORITY_UNAVAILABLE")
            remaining=min(max_attempts,MAX_ATTEMPTS_PER_LINEAGE-prior)
            if remaining<=0:
                return _deny("REFINEMENT_BUDGET_EXHAUSTED")
            parent=dict(task)
        frozen=json.loads((workspace/"artifacts"/(tid+".json")).read_bytes())
        spec=frozen["source_spec"]
        base=_sources(spec,fixtures)
        public_bytes=safe_fixture(fixtures,spec["visible"])
        public=cases_from_bytes(public_bytes)
        changes={k:v.encode() for k,v in frozen["changes"].items()}
        # Run only public examples, never open/read spec['holdout'].
        baseline=run_suite(base,{},spec["entrypoint"],public)
        if baseline["passes"]==baseline["total"]:
            return _deny("ORIGINAL_FAILURE_NOT_REPRODUCED")
        previous=run_suite(base,changes,spec["entrypoint"],public,
                           include_observed=True)
        if previous["passes"]==previous["total"]:
            return _deny("PUBLIC_ALREADY_PASSES")
        feedback=_public_feedback(changes,public,previous)
        history=[]
        seen={sha(json.dumps(frozen["change_sha256"],sort_keys=True).encode())}
        seen.update(previously_tested)
        for iteration in range(remaining):
            from .local_model import LocalModelUnavailable
            try:
                raw=_candidate_from_model(spec,base,public_bytes,model,feedback=feedback)
                changed=candidate_changes(raw,spec["files"])
                key=sha(json.dumps({p:sha(v) for p,v in changed.items()},
                                       sort_keys=True).encode())
                repeated=key in seen
                unchanged=(not changed or all(base[p]==v for p,v in changed.items()))
                if repeated or unchanged:
                    reason=("MODEL_REPEATED_PRIOR_HYPOTHESIS" if repeated
                            else "MODEL_CANDIDATE_NO_CHANGE")
                    record={"candidate_fingerprint":key,
                            "public_passes":None,"public_total":len(public),
                            "attempt":prior+iteration+1,"hidden_seen":False,
                            "rejected_reason":reason,
                            "model_origin":"LOOPBACK_ONLY_UNTRUSTED"}
                    if not _record_attempt(db_path,tid,parent,record):
                        return _deny("REVIEW_AUTHORITY_OR_BUDGET_CHANGED",
                                     attempts=len(history))
                    history.append(record)
                    seen.add(key)
                    feedback=dict(feedback)
                    feedback["latest_rejection"]={
                        "reason":reason,"candidate_fingerprint":key,
                        "retry_index":prior+iteration+1,
                        "must_propose_different_full_source":True}
                    continue
                seen.add(key)
                output=run_suite(base,changed,spec["entrypoint"],public,
                                 include_observed=True)
            except LocalModelUnavailable:
                return _deny("INSTALLED_LOCAL_MODEL_UNAVAILABLE",attempts=len(history))
            except (ValueError,UnicodeError,KeyError,TypeError):
                return _deny("MODEL_CANDIDATE_INVALID",attempts=len(history))
            record={"candidate_fingerprint":key,
                    "public_passes":output["passes"],
                    "public_total":output["total"],
                    "attempt":prior+iteration+1,
                    "hidden_seen":False,
                    "model_origin":"LOOPBACK_ONLY_UNTRUSTED"}
            if not _record_attempt(db_path,tid,parent,record):
                return _deny("REVIEW_AUTHORITY_OR_BUDGET_CHANGED",
                             attempts=len(history))
            history.append(record)
            if output["passes"]==output["total"]:
                # Freeze the successfully tested public hypothesis as a
                # new separate child task. Holdout review is STILL pending.
                return _freeze_revision(db_path,workspace,fixtures,tid,parent,
                                        spec,base,public_bytes,changed,history)
            feedback=_public_feedback(changed,public,output)
        if history[-1].get("rejected_reason"):
            return _deny(history[-1]["rejected_reason"],
                         attempts=len(history),
                         remaining_parent_budget=MAX_ATTEMPTS_PER_LINEAGE-prior-len(history))
        return _deny("PUBLIC_REFINEMENT_BUDGET_EXHAUSTED",
                     attempts=len(history),last_public_passes=history[-1]["public_passes"])
    except ContainerUnavailable as exc:
        return _deny("ISOLATION_UNAVAILABLE",reason=str(exc),no_host_execution=True)
    except (OSError,sqlite3.Error,KeyError,TypeError,ValueError,ArtifactConflict):
        return _deny("PUBLIC_REFINEMENT_EVIDENCE_UNAVAILABLE")


def _freeze_revision(db_path,workspace,fixtures,tid,parent,spec,base,visible,changed,history):
    immutable={"task_id":None,"goal_rev":parent["goal_rev"],
        "source_spec":spec,"source_sha256":{p:sha(b) for p,b in base.items()},
        "public_sha256":sha(visible),"proposal_input_sha256":None,
        "provenance":"UNTRUSTED_LOCAL_MODEL",
        "changes":{p:v.decode("utf-8") for p,v in changed.items()},
        "change_sha256":{p:sha(v) for p,v in changed.items()},
        "holdout_status":"SEALED_NOT_READ_BY_PLANNER",
        "state":"PROPOSAL_NOT_APPROVED",
        "parent_task_id":tid,
        "public_revision_attempts":[x["candidate_fingerprint"] for x in history]}
    db=connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        now=db.execute("SELECT * FROM tasks WHERE task_id=?",(tid,)).fetchone()
        auth=db.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        counts=db.execute("""SELECT COUNT(*) FROM events WHERE task_id=?
            AND kind='REPO_LOCAL_PUBLIC_REVISION_TRIAL'""",(tid,)).fetchone()[0]
        if (not now or not auth or now["state"]!="NEEDS_REVIEW"
            or now["state_version"]!=parent["state_version"]
            or now["artifact_hash"]!=parent["artifact_hash"]
            or counts>MAX_ATTEMPTS_PER_LINEAGE
            or not auth["write_allowed"] or auth["goal_rev"]!=now["goal_rev"]
            or auth["grant_rev"]!=now["grant_rev"]):
            db.commit()
            return _deny("REVISION_AUTHORITY_CHANGED_BEFORE_FREEZE")
        if ({p:sha(safe_fixture(fixtures,p)) for p in spec["files"]}!=immutable["source_sha256"]
            or sha(safe_fixture(fixtures,spec["visible"]))!=immutable["public_sha256"]):
            db.commit()
            return _deny("REVISION_SOURCE_CHANGED_BEFORE_FREEZE")
        child=create_task(db,spec,parent=tid,commit=False)
        immutable["task_id"]=child
        data=(json.dumps(immutable,sort_keys=True,indent=2)+"\n").encode()
        if len(data)>65536:
            db.rollback()
            return _deny("REVISION_ARTIFACT_TOO_LARGE")
        digest=store_once(workspace,child,data)
        db.execute("""UPDATE tasks SET state='NEEDS_REVIEW',
                 artifact_hash=?,decision='PUBLIC_FEEDBACK_LOCAL_REVISION',
                 state_version=state_version+1 WHERE task_id=?""",(digest,child))
        db.execute("""UPDATE tasks SET state='UNKNOWN',
                 error_code='PUBLIC_REVISION_SUPERSEDED',
                 state_version=state_version+1 WHERE task_id=?""",(tid,))
        event(db,tid,"REPO_REFINEMENT_PARENT_SUPERSEDED",{
            "child":child,"attempts":len(history),
            "public_evidence_only":True,"production_write_authorized":False})
        event(db,child,"REPO_REFINEMENT_PROPOSAL_FROZEN",{
            "parent":tid,"public_passes":history[-1]["public_passes"],
            "public_total":history[-1]["public_total"],
            "holdout_review_pending":True,
            "production_write_authorized":False})
        db.commit()
        return _deny("REVISED_PUBLIC_CANDIDATE_FROZEN",
                     child_task_id=child,parent_task_id=tid,
                     model_candidates_tested=len(history),
                     independent_holdout_pending=True,
                     public_passes=history[-1]["public_passes"],
                     public_total=history[-1]["public_total"])
    except BaseException:
        db.rollback();raise
    finally:db.close()
