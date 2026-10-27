# P10 — continuous behavioral conformance, whole-stack integration gate

## This increment addresses governance failure, not another domain adapter

Prior P0–P9 could declare `VERIFIED`, `NEEDS_REVIEW`,
`SANDBOX_VERIFIED` or `DECOMPOSED` even after the corresponding source,
artifact, effect receipt or parent/child relationship was changed later. A
one-time CI regression or a developer's description cannot prove that these
claims continue to be true. A partial response to one invalid task can leave
dependent tasks still running. P10 adds **running conformance enforcement**
and an **integration candidate** directed at `main`; it does not pretend
an entirely general autonomous mind has been constructed.

## Independent evidence readback

`src/cognition_agent_os/conformance.py` uses the existing SQLite authority,
original fixture and workspace to inspect these state claims:

- A `NEEDS_REVIEW` JSON/CSV repair requires read-only goal audit;
  a reconciliation proposal requires independent SQLite/source audit;
  a legacy fixture/GitHub artifact at least requires immutable bytes.
- A `SANDBOX_VERIFIED` result requires matching authoritative proposal
  checksum, the actual sandbox file bytes, unchanged source, separate
  mechanical preservation constraints and exactly one correctly-scoped
  `SANDBOX_EFFECT_VERIFIED` event with a matching effect SHA.
- A `DECOMPOSED` intent requires the independent goal-plan audit to
  recompute its event, digest, single child and parent/grant lineage.
- A `VERIFIED` typed no-op or consistent record set is checked against
  the **current** source again. Legacy fixture `NO_CHANGE` without a
  supported independent outcome readback remains
  `INSUFFICIENT_EVIDENCE`, not fabricated corruption.

Each observation is `PASS`, `INSUFFICIENT_EVIDENCE`, or
`CONFIRMED_INCONSISTENCY`. On confirmed mechanical inconsistency, the
enforcing sweep marks the root task `UNKNOWN` and traverses its entire
bounded dependency chain (up to 256 tasks), marking dependent work
`UNKNOWN`/`BLOCKED` and recording a `CONFORMANCE_VIOLATION` plus
`CONFORMANCE_DEPENDENCY_BLOCKED` events. It **does not overwrite** the
original evidence or claim to know the causal defect class.
Missing independent proof is an acceptance blocker, but is NOT treated as
proof of malicious tampering.

The P10 default host `run_tick` includes one bounded enforcing
conformance sweep **without needing the user to notice and flag** a false
task state. No parallel governance DB exists. A
`conformance_scan.last_task_id` cursor is stored in the existing SQLite
ledger and rotated across eligible tasks; a first-N bad queue cannot
permanently hide later rows. Claims of complete coverage are withheld when
the selected subset is smaller than the eligible set.

## Read-only investigation and optional manual sweep

```powershell
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures conformance-audit --max-cases 64
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace --fixtures .\fixtures conformance-audit --max-cases 64 --enforce
```

The first command is read-only, refuses to initialize a missing DB and does
not alter any task; the second explicitly opts into the same safe
quarantine that the already-authorized local host performs by default.
Neither prints a trustworthy `APPROVED_FOR_PRODUCTION` status.

## Integration candidate and release blockers

The historical PR chain #1–#11 is open/draft/unmerged. Instead of creating
a twelfth stacked feature PR, this branch is proposed directly **against
`main` as one integration candidate**. GitHub CI therefore validates the
aggregate working tree rather than only a tiny delta against P9. It remains
Draft; **no merge** or actual Windows installation is performed.

The conformance output always reports:

- `external_semantic_evidence: NOT_OBSERVED`
- `unattended_windows_host_evidence: NOT_OBSERVED`
- `production_mutation_authorized: false`
- `release_gate: BLOCKED_AWAITING_INDEPENDENT_OUTCOME_AND_HOST_PROOF`

These fields cannot be promoted based on test counts, handoffs, the Agent's
own assessment or untrusted upstream data. Release requires independent
business/domain review under separate authority, actual physical scheduled
runs and source-specific outcome evidence. SHA-pinned manifests do not
authenticate human reviewer identity. Continued local code development
does not require pretending this evidence exists.

## Acceptance tests

`tests/test_conformance.py` includes actual temporary-SQLite/source
execution; authentic sandbox success, forged state without file, changed
sandbox bytes, false effect receipt, corrupted queued proposal, upstream
parent plan falsification with automatic dependent-task quarantine, a
legitimate decomposed plan, current-source mismatch after a previous
success, insufficient legacy evidence, round-robin scans of many tasks,
and independent CLI read-only vs enforce behavior. Existing P0–P9
regressions remain required.

P10 is a **system-level safety and truthfulness increment**, not evidence
of autonomous causal method learning, open-world goal discovery,
external production action or a functioning Windows background agent.

## P10.1 systemic blast-radius response: persistent capability circuit breaker

Merely quarantining one forged task is insufficient if the same implementation
continues to act on new work. When an enforced readback catches a serious
**confirmed integrity contradiction** in a previously `SANDBOX_VERIFIED`
goal (e.g., changed sandbox bytes, false/missing effect receipt, mismatched
artifact or falsified candidate constraints), P10 also opens a durable
`goal_sandbox_stage` circuit in the SAME SQLite database:

- Exactly one initial `CONFORMANCE_CAPABILITY_DISABLED` event records the
  triggering task, integrity reason and non-self-resetting policy.
- Manual `goal-stage-sandbox` and the existing host's automatic
  `advance_due_reviews` both consult this guard. A second check inside the
  execution write lock fences a concurrent circuit trip, not just the
  caller-side precheck.
- Pending work stays pending or `NEEDS_REVIEW`, but further sandbox effects
  are **blocked**, not silently rerouted to an unchecked alternate path.
- The breaker is NOT tripped for `INSUFFICIENT_EVIDENCE` or unrelated
  unsupported historical success reports; absence of semantic proof and
  confirmed integrity violation are separate signals.
- The system contains no model-authorized automatic re-enable. Recovery
  requires a separately authorized and evidenced remediation protocol before
  a breaker-reset interface could safely be introduced.

This is a system-level safe stop rather than a guessed code patch. It avoids
another partial repair by protecting **all future tasks using the same
capability**, in addition to quarantining the already-affected task lineage.
The actual systemic root cause remains unknown until falsified/confirmed.

The dedicated negative test for a forged effect receipt proves the circuit
trips once, persists, prevents a second sandbox write and does not recur on
later sweeps. The evidence-insufficiency negative control proves no
false-positive circuit trip.

**Integration CI proof:** GitHub Actions run `39433023953` succeeded
with **169/169 Python unittest cases**, from the cumulative PR to `main`.
`live_public_source` was SKIPPED. Code correctness does not prove Windows
Task Scheduler activation, human-domain approval or production readiness.

## P10.2 — two fail-open paths corrected at the system boundary

During continued review of the cumulative integration candidate, two
substantive governance defects were identified in the previous P10 code:

1. **Unknown dependent-task blast radius.** The earlier `_descendants`
   checker raises when an ancestry graph is cyclic or exceeds the 256-task
   budget. The caller previously returned `DEPENDENCY_BUDGET_BLOCKED`,
   leaving the false success claim active and later writes permissible.
   Now this failure triggers `CONFORMANCE_EMERGENCY_STOP` in the same
   authoritative SQLite transaction: revoke the ledger-wide write grant,
   move the root claim to UNKNOWN, and persistently disable sandbox staging.
   It does **not** falsely claim to have examined or quarantined every
   descendant. Future authorized effects remain blocked pending separate
   diagnosis and acceptance. Fanout-vs-cycle remains a hypothesis, not a
   proven root cause.
2. **Check after the next effect.** The earlier host verified previous
   `SANDBOX_VERIFIED` receipts only *after* admitting new work, so a forged
   previous receipt could coexist with a new sandbox action. A new
   `effect_preflight` performs a bounded complete conformance inspection
   before an opted-in host stages effects; direct manual staging also
   requires the same preflight. If eligible claims exceed the finite
   512-item scan budget, new effects are blocked rather than pretending
   coverage is complete. A confirmed, fully contained *non-critical* bad
   review is quarantined and does not starve unrelated good tasks.
   Any still-uncontained discrepancy, an emergency stop or capability
   circuit trip prohibits effects.

Source data changing normally between proposal and review is
`INSUFFICIENT_EVIDENCE` and eligible for the existing P6/P7 bounded
source-drift replanning path; it is not presented as a forged outcome.

### Stronger acceptance

`tests/test_governance_failclosed.py` exercises a 259-child dependency
fanout, a forged cyclic dependency, direct and host-initiated new actions
after a previously verified artifact/receipt is tampered with, over-budget
512+ status claims, contained noncritical review errors followed by a valid
action, and safe source drift leading to legitimate replanning.

The first extended run `39435548093` had **174/175 passing** because an
overly strict preflight stalled safe work even after unrelated malformed
reviews were quarantined. The admission condition was corrected to allow
**only fully contained non-critical** contradictions; no circuit or
unbounded dependency case is admitted. The subsequent cumulative CI
`39435827296` passed **176/176 Python tests** with no paid AI tokens.
Live external public-source smoke was SKIPPED, not a verified upstream check.

These engineering repairs do not automatically determine the actual
cause of a corrupted task graph, repair source code, attest an external
reviewer, establish semantic business outcomes or prove physical
unattended Windows operation. No breaker-reset, hidden permission
restoration, or production merge is authorized.

## P10.3 — competing structural hypotheses, class-wide repair, independent outcome

P10.2 correctly **stopped** the ledger when the 256-dependency bound was
exceeded or a graph was cyclic, but it could not tell the two causes apart.
Legitimate deep or wide DAGs therefore suffered unnecessary global shutdown.
This was a genuine causal-policy error, not an invitation to disable limits.

`src/cognition_agent_os/graph_experiment.py` now distinguishes two
testable, competing explanations UNDER the existing `BEGIN IMMEDIATE` lock:

- **ACYCLIC_HIGH_FANOUT**: Python breadth-first traversal finds a finite
  dependency closure and the separate SQLite recursive CTE produces exactly
  the same nodes, with an independent ancestor-chain cycle exclusion.
- **DEPENDENCY_CYCLE**: a repeated graph node and ancestor traversal both
  establish an actual cycle. Neither a guessed edge removal nor a broad
  silent repair is permitted.

The hard experimental budget is **4096 graph nodes**, including the root.
Oracle disagreement, CTE failure, missing lineage evidence or exceeding
the cap is an **UNVERIFIABLE** outcome that maintains global fail-closed
protection.

For an independently proven **acyclic** graph that exceeded the previous
256-child soft limit, the original root and **all actual descendants**
are quarantined atomically, rather than revoking the ledger-wide grant.
The reasoned choice, competing falsified/not-falsified hypotheses, scope
hash and outcome are persisted in `CONFORMANCE_GRAPH_EXPERIMENT` events.

Crucially, executing the repair is NOT its success evidence:
`verify_local_quarantine` independently recomputes the full closure
using SQL and checks the *actual SQLite states* of every descendant.
Only a complete match writes a `CONFORMANCE_REPAIR_ACCEPTED` event.
An incomplete effect instead records `CONFORMANCE_REPAIR_REJECTED`
and escalates to the same global emergency revoke/circuit as P10.2.
There is no automatic reset, production write, self-issued semantic
approval or unauthorized graph surgery.

### Acceptance and falsification

`tests/test_graph_experiment.py` runs previously unseen graph shapes
(wide fanout, deep chain, multilevel branching), a real cyclic graph,
two independent oracles disagreeing, independent SQL failure, a graph
exceeding the experiment cap, and an intentionally **partially executed
repair** whose post-action audit rejects it. The earlier 259-dependent
regression now asserts full local containment and that unrelated writes
remain authorized. The cyclic regression still requires global stop.
The existing P0–P10 regression suite is not replaced.

Cumulative integration CI
`39437997734`: **182/182 Python tests PASS**.
The live public-source job was SKIPPED, not freshly verified.

**Boundary of the claim:** these are independently cross-checked
*structural* hypotheses for an existing task ledger, not validated causes
of the user's real-world goals, independent business semantics, general
code synthesis or an approved production repair. Durable history records
a verified **method choice**, not machine-learned open-world strategies.
Release/Windows-host/third-party review gates remain BLOCKED.
