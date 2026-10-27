# cognition-agent-os P0/P1 prototype (draft)

This is a **bounded, non-daemon, zero-LLM, zero-paid-provider prototype**. It is not the completed autonomous controller. It implements a trustworthy beginning of one research/evidence task path, not self-directed unknown-risk discovery.

## Run locally (Python >=3.10, standard library)

```bash
export PYTHONPATH=src
mkdir -p /tmp/cognition-fixtures
printf 'protocol v1\n' > /tmp/cognition-fixtures/old.txt
printf 'protocol v2\n' > /tmp/cognition-fixtures/new.txt
python -m cognition_agent_os.cli --db /tmp/cognition-lab/state.db --workspace /tmp/cognition-lab --fixtures /tmp/cognition-fixtures seed-fixture --old old.txt --new new.txt
python -m cognition_agent_os.cli --db /tmp/cognition-lab/state.db --workspace /tmp/cognition-lab --fixtures /tmp/cognition-fixtures worker-once
python -m cognition_agent_os.cli --db /tmp/cognition-lab/state.db --workspace /tmp/cognition-lab status
python -m unittest discover -s tests -v
```

**GitHub public source mode**: `seed-github --repo owner/name --path path/to/file --old-ref FULL40CHARCOMMIT --new-ref FULL40CHARCOMMIT`; upstream reads use only api.github.com and SHA-verified GitHub base64 content, not arbitrary URLs. GitHub API network access is required for execution (the test suite uses local fixtures).

## Real behavior and boundaries

- SQLite holds authoritative task state, target goal version, revocable local write grant, optimistic claiming/lease, event history, and optional recurrence. Every `worker-once` call needs a **real host/user invocation**. Recurrence stores a future task, **not** a wake guarantee.
- For equal source bytes the result is `VERIFIED/NO_CHANGE` without fabricating a report. For changed bytes the deterministic diff adapter creates `NEEDS_REVIEW/CHANGE_REQUIRES_REVIEW` after authorized immutable local artifact write + readback. **No real LLM has evaluated its semantic impact.**
- The local file write is serialized under the authority DB write transaction. Crash after file write/before DB commit is reconciled by exact byte readback under the same task ID. This is not a third-party exactly-once guarantee.
- Unknown source/identity or artifact mismatch is `UNKNOWN`, never a fake successful change. Stale goal and revoked write grant block effects. Artifact bytes are read back and hashed; this is **not** an independent third-party evaluation of user outcomes.
- Public repo only: keep test data synthetic, never commit state.db, artifacts/, tokens, private content. No workflow schedule, unattended host, model keys or paid calls are enabled.
- Remaining risks: lease expiry/fencing under slow long writes, cross-database and remote side effects, filesystem full/disconnect, crash durability under power loss, independent host trigger, real LLM behavior, provider billing and human-independent semantic oracle. All must be tested in later phases before autonomy claims.
