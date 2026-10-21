"""Native GitHub Linux Docker proof for whole-file repository repair.

This actually executes untrusted whole-file Python inside a Docker container,
not on the host, with hidden EXPECTED outputs compared in the host-only
oracle. No model, cloud inference, user credentials or production repo writes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from cognition_agent_os.container_lab import run_suite,IMAGE
from cognition_agent_os.ledger import connect,initialize,create_task
from cognition_agent_os.runner import run_once
from cognition_agent_os.repo_repair import review_repo,audit_repo
from cognition_agent_os.conformance import inspect_conformance


def require(condition,message):
    if not condition:
        raise RuntimeError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="cognition-real-docker-") as temp:
        base=Path(temp)
        fx=base/"fx";fx.mkdir()
        ws=base/"workspace";ws.mkdir()
        db=base/"tasks.sqlite"
        entry=(b"import json,sys\nfrom rules import calculate\n"
               b"print(json.dumps(calculate(json.loads(sys.stdin.read()))))\n")
        broken=b"def calculate(data):\n    return {'net':0}\n"
        fixed=(
            "def calculate(data):\n"
            "    by_group = {}\n"
            "    for row in data['rows']:\n"
            "        value = row['amount']\n"
            "        if row['kind'] == 'debit':\n"
            "            value = -value\n"
            "        name = row['group']\n"
            "        by_group[name] = by_group.get(name, 0) + value\n"
            "    return {'by_group': by_group, 'net': sum(by_group.values())}\n")
        fx.joinpath("main.py").write_bytes(entry)
        fx.joinpath("rules.py").write_bytes(broken)
        candidate={"changes":[{"path":"rules.py","content":fixed}]}
        fx.joinpath("proposal.json").write_bytes(json.dumps(candidate).encode())
        public=[
            {"input":{"rows":[{"kind":"credit","amount":12,"group":"hardware"},
                              {"kind":"debit","amount":5,"group":"hardware"}]},
             "expected":{"by_group":{"hardware":7},"net":7}},
            {"input":{"rows":[]},"expected":{"by_group":{},"net":0}}
        ]
        hidden=[
            {"input":{"rows":[{"kind":"debit","amount":3,"group":"groceries"},
                              {"kind":"credit","amount":50,"group":"software"}]},
             "expected":{"by_group":{"groceries":-3,"software":50},"net":47}},
            {"input":{"rows":[{"kind":"credit","amount":15,"group":"travel"},
                              {"kind":"debit","amount":4,"group":"travel"}]},
             "expected":{"by_group":{"travel":11},"net":11}}
        ]
        fx.joinpath("visible.json").write_bytes(json.dumps(public).encode())
        gold_bytes=json.dumps(hidden).encode()
        fx.joinpath("hidden.json").write_bytes(gold_bytes)
        spec={"kind":"repo_container_repair",
              "files":["main.py","rules.py"],"entrypoint":"main.py",
              "candidate":"proposal.json","visible":"visible.json",
              "holdout":"hidden.json",
              "holdout_sha256":hashlib.sha256(gold_bytes).hexdigest()}
        connection=connect(db);initialize(connection)
        task_id=create_task(connection,spec)
        connection.close()
        planned=run_once(db,ws,fx)
        require(planned["status"]=="NEEDS_REVIEW",f"Planning failed: {planned}")
        require(planned["holdout_seen_by_planner"] is False,
                "Planner must not open hidden tests")
        audited=audit_repo(db,ws,fx,task_id)
        require(audited["status"]=="REPO_BYTES_MECHANICALLY_VALID",
                f"Immutable input check failed: {audited}")
        accepted=review_repo(db,ws,fx,task_id)
        require(accepted["status"]=="REPAIR_LAB_VERIFIED",
                f"Real Docker holdout did not pass: {accepted}")
        require(accepted["holdout_passes"]==2,
                "Expected two actual hidden outputs to match")
        require(fx.joinpath("rules.py").read_bytes()==broken,
                "Original code must be unchanged")
        require(ws.joinpath("repo_lab",task_id,"rules.py").read_bytes()==fixed.encode(),
                "Staged whole-file patch bytes differ")
        check=inspect_conformance(db,ws,fx)
        require(check["mechanically_valid"]==1,
                "Independent ledger record verification did not pass")
        print(json.dumps({"test":"actual_repo_container_program",
            "status":"PASS","image":IMAGE,
            "original_sources_unchanged":True,
            "public_outputs_checked_on_host":len(public),
            "hidden_outputs_checked_on_host":len(hidden),
            "staged_source_promotion":False},sort_keys=True))

        # A candidate cannot reach the network, modify its mounted source,
        # see a hidden gold file, or acquire root privileges.
        probe=(
            b"import json,os,socket,sys\n"
            b"json.loads(sys.stdin.read())\n"
            b"network_blocked=False\n"
            b"try:\n"
            b"    s=socket.create_connection(('1.1.1.1',443),timeout=0.5)\n"
            b"    s.close()\n"
            b"except OSError:\n"
            b"    network_blocked=True\n"
            b"writes_blocked=False\n"
            b"try:\n"
            b"    open('/app/probe.py','wb').write(b'injected')\n"
            b"except OSError:\n"
            b"    writes_blocked=True\n"
            b"print(json.dumps({'network_blocked':network_blocked,"
            b"'mount_readonly':writes_blocked,'uid':os.getuid(),"
            b"'gold_visible':os.path.exists('/app/hidden.json')}))\n"
        )
        observed=run_suite({"probe.py":probe,"support.py":b"# original\n"},
                           {},"probe.py",[
            {"input":{"task":"observe_isolation"},
             "expected":{"network_blocked":True,
                         "mount_readonly":True,"uid":65534,
                         "gold_visible":False}}
        ])
        require(observed["passes"]==1,
                f"Container escaped isolation limits: {observed}")
        print(json.dumps({"test":"real_network_user_readonly_no_gold",
                          "status":"PASS","image":IMAGE,
                          "no_host_fallback":True},sort_keys=True))

        # Separate frozen candidate: matches visible, but fails unseen
        # gold for a different category; container never receives expected
        # hidden values, so the owner-side oracle must reject it.
        wrong=fixed.replace("for row in data['rows']:",
                            "for row in data['rows']:\n"
                            "        if row['group'] != 'hardware':\n"
                            "            continue")
        fx.joinpath("proposal.json").write_bytes(json.dumps({
            "changes":[{"path":"rules.py","content":wrong}]
        }).encode())
        next_id=create_task(connect_and_close(db),spec) if False else None
        connection=connect(db)
        next_id=create_task(connection,spec)
        connection.close()
        planned=run_once(db,ws,fx)
        require(planned["status"]=="NEEDS_REVIEW",
                f"Negative candidate did not freeze: {planned}")
        result=review_repo(db,ws,fx,next_id)
        require(result["status"]=="HOLDOUT_REFUTED",
                f"Incorrect public-fit candidate was not refuted: {result}")
        require(not (ws/"repo_lab"/next_id).exists(),
                "Refuted patch must not be staged")
        print(json.dumps({"test":"real_public_fit_hidden_refutation",
                          "status":"PASS","image":IMAGE,
                          "failed_candidate_not_staged":True},sort_keys=True))


if __name__=="__main__":
    main()
