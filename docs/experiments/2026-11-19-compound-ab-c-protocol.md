# S2 — Compound Owner Goal A/B/C Experiment Protocol

**Status:** preregistered protocol; real-model execution pending.  
**Candidate branch:** `work/s2-compound-owner-oracle-20261119`  
**Draft review:** PR #66, stacked on PR #65.  
**Purpose:** compare the incumbent deterministic route, the current Native Planner, and a thin OpenAI Agents SDK/MCP orchestration candidate on one bounded compound local task.

This is an architecture screen, not a product acceptance test or final architecture decision.

## 1. Fixed owner task and inputs

The experiment uses the predeclared `compound_owner_goal_two_independent_effects` case in `ORACLE_SCOPE_PROBES`:

1. Compare `baseline.csv` with `actual.csv` and produce a source-pinned discrepancy report.
2. Then stage a separate `settings.json` candidate that preserves the original fields and adds the owner-pinned field.

All arms receive identical fixture bytes and the exact same owner-goal text. Each arm receives a fresh isolated temporary directory and SQLite ledger. No production data is used.

## 2. Arms

### A — incumbent deterministic route

- Creates the incumbent `open_goal` root.
- Runs the existing Host in deterministic mode.
- Uses no model.
- The independent oracle accepts only if the actual SQLite lineage and artifacts satisfy the complete compound contract.

### B — current Native Planner

- Registers the same owner goal through the existing native-goal contract.
- Uses the current native planner with the local Ollama model.
- Uses the existing Host/Worker path and the same source, grant and registered capabilities.
- Allows at most two sequential native decisions, followed by the ordinary sandbox review tick.

### C — Agents SDK over the existing MCP bridge

- Registers the same native goal with a managed local session.
- Uses OpenAI Agents SDK 0.25.0 with Chat Completions mode against the same local Ollama model.
- Uses the existing stdio MCP bridge, SQLite ledger, admission function, targeted Worker and sandbox boundary.
- Does not create a second database, grant, scheduler, Worker, or effect system.

The MCP client allowlist is deliberately narrow:

- `native_goal_inspect`
- `native_procedure_evidence`
- `native_owner_outcome`
- `native_capabilities`
- `native_source_read`
- `native_decision_admit`
- `native_local_tick`

Root creation, generic native model planning, memory writes, public-source access, arbitrary shell and external connectors are not exposed to C.

## 3. Fairness and resource bounds

- B and C use the same model identifier: `qwen2.5:3b`.
- All arms use the same exact goal text, source bytes, source hashes, owner-goal hash and initial SQLite authority revision.
- The same 600-second wall-clock budget applies to each arm.
- B is limited to two sequential decisions. C is limited to 18 model turns and 900 output tokens per turn. Each B/C model request is bounded at 240 seconds within the 600-second per-arm wall-clock ceiling.
- The order of B and C is deterministically shuffled from the owner-goal hash and recorded. Ollama requests are asked to unload the model after each turn where supported.
- Actual model calls, token counts where reported, tool calls, elapsed time, selected objectives, task states, lineage and errors are recorded. Missing token telemetry is reported as unavailable, never inferred.
- A runs without a model as the incumbent deterministic baseline.

The orchestration surfaces differ by design: B uses the current planner/Host path; C uses the SDK loop and a narrow MCP tool surface. The registered local capabilities, source corpus, authority revision and Worker effect boundary remain the same.

## 4. Security and effect boundary

- Ollama is loopback-only. The SDK endpoint validator rejects non-loopback and HTTPS endpoints.
- No cloud model API, paid inference API, API key, production grant, user data, deployment or user-machine installation is used.
- Agent tracing is disabled.
- A rejected native decision returns a fixed safe schema-recovery message; it does not disclose internal exception text, weaken validation, or authorize a tick. C may correct a rejected proposal only while source, observation and authority snapshots remain current.
- The MCP subprocess receives only `PATH`, `HOME`, `PYTHONPATH`, `PYTHONUNBUFFERED` and `PYTHONUTF8`; ambient runner credentials are not forwarded.
- The only write tools are native decision admission and one-root targeted local Worker execution. Both still require the current SQLite grant and managed-session contract.
- All effects remain local candidates. Original source files must remain byte-identical.

## 5. Independent acceptance oracle

The evaluator is outside the CAOS runtime and does not import the planner, Host, Worker, intent compiler or owner-postcondition implementation.

A pass requires all of the following:

1. Exactly two direct child tasks under the original root.
2. Child insertion order is CSV reconciliation first, JSON draft second.
3. Both children share the exact original root, goal revision and grant revision.
4. The CSV artifact is independently recomputed from the two pinned source files and matches the expected child ID and artifact hash.
5. The JSON artifact and sandbox candidate preserve all original fields and add the owner-pinned field.
6. The JSON child reaches `SANDBOX_VERIFIED`; the CSV child reaches its expected review state.
7. Every original source hash remains unchanged.
8. No extra child, missing child, duplicate task ID, path escape or mismatched provenance is present.

The positive label is `SYNTHETIC_COMPOUND_OWNER_GOAL_MET`. It proves only these synthetic local postconditions. It does not prove semantic correctness outside the declared contract, real owner acceptance, delivery, external business outcome, or product readiness.

## 6. Interpretation rules

- A/B/C results are not selected by the model's final prose. The independent oracle and actual ledger/artifact bytes determine the local result.
- A failed or incomplete arm is retained as evidence; it is not silently retried or replaced.
- Compare success, order correctness, source preservation, lineage, model calls, tokens, tool calls, elapsed time and failure modes.
- One synthetic task cannot select a final CAOS architecture. Any apparent winner must be challenged on the other preregistered task groups: unfamiliar software defect, cross-source research, and method transfer/rollback.
- A green engineering CI is not a product-ready claim.
- No merge, release or deployment is authorized by this experiment.

## 7. Expected artifact

The opt-in GitHub Actions job uploads `compound-ab-c-evidence.json` with all three arms, independent verdicts, tool/decision traces, usage telemetry and explicit non-claims. The job is optional and separately classified by the CI evidence-scope receipt.
