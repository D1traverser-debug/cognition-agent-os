"""Real HTTPS P34 -> P35 research path smoke; synthetic evidence, NOT semantic verification."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
from contextlib import closing

from cognition_agent_os.host import run_tick
from cognition_agent_os.ledger import connect, create_task, initialize

REPO = "D1traverser-debug/cognition-agent-os"
REF = "15cce423b9798307eb4f4b0a1d26775cce54643b"
SOURCE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

def main():
    with tempfile.TemporaryDirectory(prefix="p36-live-research-") as tmp:
        root=Path(tmp)
        fixtures=root/"fixtures"
        fixtures.mkdir()
        workspace=root/"workspace"
        db_path=root/"task.sqlite"
        (fixtures/"structure.json").write_text('{"keep":42}')
        (fixtures/"before.csv").write_text("id,amount\nA,1\n")
        (fixtures/"after.csv").write_text("id,amount\nA,2\n")
        knowledge={"schema_version":1,"source_id":"seeded",
                   "claims":[{"goal_key":"unrelated-goal","route":"structure",
                              "status":"active","source_ref":"synthetic:seed"}]}
        raw=json.dumps(knowledge,sort_keys=True).encode()
        (fixtures/"knowledge.json").write_bytes(raw)
        sources=[]
        for suffix,publisher in (("a","synthetic-alpha"),("b","synthetic-beta")):
            name="p36_public_"+suffix+".json"
            data=(SOURCE_DIR/name).read_bytes()
            sources.append({"kind":"github","repo":REPO,"ref":REF,
                            "path":"tests/fixtures/"+name,
                            "sha256":hashlib.sha256(data).hexdigest(),
                            "source_id":"p36_public_"+suffix,"publisher_id":publisher})
        spec={"kind":"knowledge_intent","goal_key":"repair-goal","research_on_gap":True,
              "knowledge":{"path":"knowledge.json","sha256":hashlib.sha256(raw).hexdigest(),
                           "source_id":"seeded"},
              "research_sources":sources,
              "options":[
                  {"route":"structure","intent":{"kind":"goal_intent","objective":"ensure_structure",
                   "resources":[{"role":"input","path":"structure.json"}],
                   "requirements":[{"field":"owner","equals":"ops"}]}},
                  {"route":"compare","intent":{"kind":"goal_intent","objective":"compare_records",
                   "resources":[{"role":"reference","path":"before.csv"},
                                {"role":"observed","path":"after.csv"}]}}]}
        with closing(connect(db_path)) as db:
            initialize(db)
            root_id=create_task(db,spec)
        tick=run_tick(db_path,workspace,fixtures,max_jobs=2)
        assert [t["status"] for t in tick["tasks"]]==["RESEARCH_NEEDED","NEEDS_REVIEW"],tick
        research_id=tick["tasks"][0]["research_task_id"]
        with closing(connect(db_path)) as db:
            child=db.execute("SELECT task_id FROM tasks WHERE parent_task=?",
                             (research_id,)).fetchone()
            assert child is not None
            assessment_id=child["task_id"]
        result=run_tick(db_path,workspace,fixtures,max_jobs=1)
        assert [t["status"] for t in result["tasks"]]==["NEEDS_REVIEW"],result
        report=json.loads((workspace/"artifacts"/(assessment_id+".json")).read_text())
        assert report["reason"]=="CONSENSUS_PENDING_EXTERNAL_SEMANTIC_REVIEW",report
        assert report["candidate_route_for_review"]=="structure",report
        assert not report["source_independence_verified"] and not report["production_effect_authorized"]
        assert not report["business_outcome_verified"]
        from cognition_agent_os.research_assessment import audit_assessment
        audit=audit_assessment(db_path,workspace,fixtures,assessment_id)
        assert audit["status"]=="ASSESSMENT_MECHANICALLY_VALID",audit
        print(json.dumps({"status":"PUBLIC_HTTPS_P34_P35_REVIEW_ONLY","source_repo":REPO,
            "pinned_commit":REF,"source_count":2,"sources":"SYNTHETIC_SELF_PUBLISHED",
            "original_task":root_id,"assessment":"NEEDS_REVIEW",
            "independent_audit":audit["status"],"semantic_independence":"NOT_PROVEN",
            "production_effect_authorized":False},sort_keys=True))
if __name__ == "__main__":
    main()
