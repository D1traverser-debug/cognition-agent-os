"""Mechanically independent causal experiments for dependency-graph overflow.

The real fault family is not presumed from a generic >256 exception.
Under the caller's authoritative SQLite BEGIN IMMEDIATE lock this module:
  - measures the forward dependency graph with bounded Python BFS,
  - independently recomputes reachable tasks via SQLite recursive CTE,
  - checks cycles separately via the ancestor chain rooted at the subject,
  - selects complete local quarantine ONLY for two matching, acyclic proofs.
It neither rewrites task parentage nor turns a candidate into a business fix.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

MAX_GRAPH_EXPERIMENT_NODES=4096


def _python_closure(db: sqlite3.Connection, root: str, limit: int):
    seen={root}
    pending=[root]
    graph={}
    revisited=False
    while pending:
        parent=pending.pop(0)
        children=[row[0] for row in db.execute(
            "SELECT task_id FROM tasks WHERE parent_task=? ORDER BY task_id",(parent,))]
        graph[parent]=children
        for child in children:
            if child in seen:
                revisited=True
                continue
            seen.add(child)
            if len(seen)>limit:
                return None,"NODE_BUDGET_EXHAUSTED"
            pending.append(child)
    return (seen,graph,revisited),"COMPLETE"


def _sql_closure(db: sqlite3.Connection, root: str, limit: int):
    # UNION (not UNION ALL) terminates even if an inherited parent pointer
    # forms a cycle. SQLite LIMIT bounds emitted rows independently of BFS.
    rows=db.execute("""
        WITH RECURSIVE dependency(id) AS (
          SELECT task_id FROM tasks WHERE task_id=?
          UNION
          SELECT child.task_id FROM tasks AS child
             JOIN dependency AS parent ON child.parent_task=parent.id
          LIMIT ?
        ) SELECT id FROM dependency ORDER BY id
    """,(root,limit+1)).fetchall()
    ids={r[0] for r in rows}
    if len(ids)>limit:
        return None,"NODE_BUDGET_EXHAUSTED"
    return ids,"COMPLETE"


def _ancestor_cycle(db: sqlite3.Connection, root: str, limit: int):
    seen=set()
    node=root
    for _ in range(limit+1):
        if node is None:
            return False,"COMPLETE"
        if node in seen:
            return True,"COMPLETE"
        seen.add(node)
        row=db.execute("SELECT parent_task FROM tasks WHERE task_id=?",(node,)).fetchone()
        if row is None:
            return None,"MISSING_ANCESTOR"
        node=row[0]
    return None,"ANCESTOR_BUDGET_EXHAUSTED"


def investigate_dependency_graph(db: sqlite3.Connection, root: str) -> dict:
    """Return a read-only experiment record; NEVER changes the authority."""
    root_row=db.execute("SELECT task_id FROM tasks WHERE task_id=?",(root,)).fetchone()
    if not root_row:
        return {"status":"UNVERIFIABLE","action":"GLOBAL_FAIL_CLOSED",
                "reason":"ROOT_MISSING","hypotheses":[]}
    py,ps=_python_closure(db,root,MAX_GRAPH_EXPERIMENT_NODES)
    sql,ss=_sql_closure(db,root,MAX_GRAPH_EXPERIMENT_NODES)
    cyclic,cs=_ancestor_cycle(db,root,MAX_GRAPH_EXPERIMENT_NODES)
    if ps!="COMPLETE" or ss!="COMPLETE" or cs!="COMPLETE":
        return {"status":"UNVERIFIABLE","action":"GLOBAL_FAIL_CLOSED",
                "reason":"BOUNDED_EXPERIMENT_INCOMPLETE",
                "hypotheses":[
                   {"mechanism":"ACYCLIC_HIGH_FANOUT","falsified":None},
                   {"mechanism":"DEPENDENCY_CYCLE","falsified":None}],
                "evidence":{"python":ps,"sqlite_recursive":ss,"ancestor":cs}}
    py_nodes,adjacency,revisited=py
    if py_nodes!=sql:
        return {"status":"ORACLE_DISAGREEMENT","action":"GLOBAL_FAIL_CLOSED",
                "reason":"INDEPENDENT_GRAPH_RECOMPUTATION_MISMATCH",
                "hypotheses":[
                    {"mechanism":"ACYCLIC_HIGH_FANOUT","falsified":None},
                    {"mechanism":"DEPENDENCY_CYCLE","falsified":None}]}
    # In this schema, each node has at most one parent, so a revisited
    # descendant means an actual cycle. Verify via independent ancestor walk.
    if bool(revisited)!=bool(cyclic):
        return {"status":"ORACLE_DISAGREEMENT","action":"GLOBAL_FAIL_CLOSED",
                "reason":"CYCLE_PROOF_MISMATCH",
                "hypotheses":[]}
    # Build snapshot only from bounded observed edges. Do not sweep the
    # entire task ledger, which may have millions of unrelated tasks.
    parent_of={root:db.execute("SELECT parent_task FROM tasks WHERE task_id=?",
                               (root,)).fetchone()[0]}
    for parent,children in adjacency.items():
        for child in children:
            parent_of[child]=parent
    snapshot=[[id,parent_of[id]] for id in sorted(py_nodes)]
    digest=hashlib.sha256(json.dumps(snapshot,separators=(",",":")).encode()).hexdigest()
    if cyclic:
        return {"status":"CYCLE_CONFIRMED","action":"GLOBAL_FAIL_CLOSED",
                "reason":"DEPENDENCY_CYCLE_CONFIRMED",
                "root":root,"nodes":len(py_nodes),"snapshot_sha256":digest,
                "hypotheses":[
                    {"mechanism":"ACYCLIC_HIGH_FANOUT","falsified":True},
                    {"mechanism":"DEPENDENCY_CYCLE","falsified":False}]}
    return {"status":"ACYCLIC_GRAPH_PROVEN","action":"COMPLETE_LOCAL_QUARANTINE",
            "reason":"LARGE_ACYCLIC_LINEAGE",
            "root":root,"nodes":len(py_nodes),"snapshot_sha256":digest,
            "descendants":sorted(py_nodes-{root}),
            "hypotheses":[
                {"mechanism":"ACYCLIC_HIGH_FANOUT","falsified":False},
                {"mechanism":"DEPENDENCY_CYCLE","falsified":True}],
            "verification":"PYTHON_BFS_AND_SQLITE_RECURSION_WITH_ANCESTOR_PROOF"}


def verify_local_quarantine(db: sqlite3.Connection, root: str,
                            expected_descendants: list[str]) -> dict:
    """Independent post-effect readback against SQLite recursive closure.

    Do not accept the repair procedure's returned count as proof of result.
    Any missing row, still-runnable descendant, new graph edge or oracle
    budget overflow returns non-acceptance. Caller must then fail globally.
    """
    ids,why=_sql_closure(db,root,MAX_GRAPH_EXPERIMENT_NODES)
    if why!="COMPLETE" or ids is None:
        return {"accepted":False,"reason":"POST_EFFECT_GRAPH_UNVERIFIABLE"}
    actual=ids-{root}
    if actual!=set(expected_descendants) or len(expected_descendants)!=len(actual):
        return {"accepted":False,"reason":"POST_EFFECT_LINEAGE_MISMATCH"}
    root_row=db.execute("SELECT state FROM tasks WHERE task_id=?",(root,)).fetchone()
    if not root_row or root_row["state"]!="UNKNOWN":
        return {"accepted":False,"reason":"ROOT_CLAIM_STILL_ACTIVE"}
    for descendant in actual:
        row=db.execute("SELECT state FROM tasks WHERE task_id=?",(descendant,)).fetchone()
        if not row or row["state"] not in ("UNKNOWN","BLOCKED"):
            return {"accepted":False,"reason":"DEPENDENT_ACTION_STILL_ACTIVE"}
    return {"accepted":True,"checked":len(actual),
            "evidence":"SQLITE_POST_ACTION_CLOSURE_AND_ACTUAL_TASK_STATES"}
