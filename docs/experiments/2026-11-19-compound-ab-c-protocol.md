# S2 — Compound Owner Goal A/B/C Experiment Protocol

**Status:** revised protocol; exact-head engineering and real-model rerun pending.  
**Candidate branch:** `work/s2-compound-owner-oracle-20261119`  
**Draft review:** PR #66, stacked on PR #65.  
**Purpose:** compare the incumbent deterministic route, the current Native Planner, and a thin OpenAI Agents SDK/MCP decision client on one bounded compound local task.

This is an architecture screen, not a product acceptance test or final architecture decision.

## 1. Fixed owner task and inputs

The experiment uses the predeclared `compound_owner_goal_two_independent_effects` case in `ORACLE_SCOPE_PROBES`:

1. Compare `baseline.csv` with `actual.csv` and produce a source-pinned discrepancy report.
2. Then stage a separate `settings.json` candidate that preserves the original fields and adds `owner="ops"`.

All arms receive identical fixture bytes and exact owner-goal text. Each arm receives a fresh isolated temporary directory and SQLite ledger. No production data is used.

## 2. Arms

### A — incumbent deterministic route

- Creates the incumbent `open_goal` root.
- Runs the existing Host in deterministic mode.
- Uses no model.
- The independent oracle accepts only if actual SQLite lineage and artifacts satisfy the complete compound contract.

### B — current Native Planner

- Registers the same owner goal through the existing native-goal contract.
- Uses `advance_native_local_once` with the local Ollama model and structured output.
- Uses the existing Host/Worker path and the same source, grant and registered capabilities.
- Allows at most two sequential native decisions, followed by the ordinary sandbox review tick.
- Native model request ceiling is 240 seconds; the planner rejects any caller timeout above this bound.

### C — Agents SDK over the existing MCP bridge

- Registers the same native goal with a managed local session.
- Uses OpenAI Agents SDK 0.25.0 with Chat Completions mode against the same local Ollama model.
- Uses the existing stdio MCP bridge, SQLite ledger and native admission function.
- The model-visible allowlist contains four bounded native read tools, one cognition-session read tool, one additive cognition-node record tool, and one native decision-admission tool:
  - `native_goal_inspect`
  - `native_procedure_evidence`
  - `native_capabilities`
  - `native_source_read`
  - `cognition_session_inspect`
  - `cognition_node_record`
  - `native_decision_admit`
- `native_local_tick` is deliberately NOT exposed to the model. The harness invokes that existing MCP tool only after it independently reads the root and confirms `NATIVE_AWAITING_WORKER`. The harness never creates a new Worker or execution authority.
- Root creation, generic native model planning, memory writes, public-source access, arbitrary shell and external connectors are not exposed to C.

## 3. Fairness and resource bounds

- B and C use the same model identifier: `qwen2.5:3b`.
- All arms use the same exact goal text, source bytes, source hashes, owner-goal hash and initial SQLite authority revision.
- B and C use the same 240-second per-model-request ceiling and 600-second per-arm wall-clock ceiling.
- B is limited to two sequential decisions. C is limited to 18 model turns and 900 output tokens per turn; the SDK loop is segmented into at most two model turns before the harness regains control and inspects the real ledger.
- The order of B and C is deterministically shuffled from the owner-goal hash and recorded. Ollama requests are asked to unload the model after each turn where supported.
- Actual model calls, token counts where reported, tool calls, argument *shapes* (not argument values), elapsed time, selected objectives, task states, lineage and errors are recorded. Missing token telemetry is reported as unavailable, never inferred.
- A runs without a model as the incumbent deterministic baseline.

The orchestration surfaces differ by design: B uses the current planner/Host path; C uses the SDK decision loop, a narrow MCP tool surface and harness-owned execution. The registered local capabilities, source corpus, authority revision and Worker effect boundary remain the same.

## 4. Security and effect boundary

- Ollama is loopback-only. The SDK endpoint validator rejects non-loopback and HTTPS endpoints.
- No cloud model API, paid inference API, API key, production grant, user data, deployment or user-machine installation is used.
- Agent tracing is disabled.
- The MCP decision-admission argument is now a strict nested TypedDict schema. The published tool schema specifies top-level proposal fields, source-reference objects, intent resources, decision basis and prior-decision review objects. Extra keys are forbidden by schema and remain independently rejected by native admission.
- A rejected native decision returns fixed safe schema-recovery guidance; it does not disclose internal exception text, weaken validation, or authorize execution. A corrected proposal is allowed only while source, observation and authority snapshots remain current.
- The MCP subprocess receives only `PATH`, `HOME`, `PYTHONPATH`, `PYTHONUNBUFFERED` and `PYTHONUTF8`; ambient runner credentials are not forwarded.
- The model cannot call `native_local_tick`. The harness calls it only after a fresh native-state read says `NATIVE_AWAITING_WORKER`; the MCP tool independently rechecks the same root, grant and pending child.
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

The positive label is `SYNTHETIC_COMPOUND_OWNER_GOAL_MET`. It proves only these synthetic local postconditions. It does not prove semantic correctness outside the declared contract, real owner acceptance, delivery, external business outcome, cross-domain transfer, fresh ChatGPT-session activation, or product readiness.

## 6. Previous real-model evidence and interpretation

The previous Qwen2.5 3B screens are retained as failures, not silently replaced:

- Actions run `44476189251`: A did not create a child. B timed out at its then-120-second planner request limit before a model response. C made eight MCP calls, but native decision admission was rejected as `UNSUPPORTED_UNGROUNDED_DECISION`; C's next model request timed out. All three independent verdicts were `NOT_ACCEPTED`.
- Actions run `44477492798`, artifact `14507129097`: A's deterministic route returned `LOCAL_MODEL_UNAVAILABLE` and created no child. B was refused immediately with `INVALID_NATIVE_MODEL_TIMEOUT` because the experiment passed 240 seconds while the planner still capped requests at 120; B made zero model calls. C made five model calls and 17 MCP calls over 600 seconds, but created no child. It had two `UNSUPPORTED_UNGROUNDED_DECISION` rejections, generic `native_capabilities` tool errors, and an attempted premature tick that the native state gate rejected. All three independent verdicts remained `NOT_ACCEPTED`. Original source hashes remained unchanged and B/C had the same effect-contract hash.

These results exposed three integration defects rather than a passing architecture: the B timeout ceiling disagreed with the experiment, the MCP decision tool published a generic dictionary rather than its actual nested contract, and the SDK's internal tool loop could consume the entire arm budget before the independent harness regained control.

The current candidate addresses those defects by aligning B's hard timeout ceiling to 240 seconds, publishing strict nested MCP argument schemas, segmenting SDK execution into two-turn intervals, removing Worker execution from the model-visible tool list, and having the harness inspect and execute only a confirmed pending child. The exact-head rerun must determine whether these changes actually improve the independent verdict.

## 6.1. 2026-11-23 upstream decision-gate falsification and correction

A new *no-model* positive-control test exercises the same managed root, scoped operator effect contract, original fixtures, native MCP decision body and SQLite. The deliberately incomplete probe called `native_decision_admit` after reading source/procedure evidence **without** recording a current cognitive decision. On exact commit `3180a6577b416ff5b284e360b85d37e13fb31ab6`, Linux CI emitted `CURRENT_COGNITIVE_DECISION_REQUIRED` at `effect_contract.enforce_admission`. This rejects the hypothesis that a syntactically grounded native proposal alone can ever reach execution on a managed root. It is a **correct security gate**, not permission to remove a check.

The pre-correction C allowlist had neither `cognition_session_inspect` nor `cognition_node_record`; the original model-visible surface could not satisfy this prerequisite, even with a perfect native decision proposal. Its absence is a demonstrable interface/permission-path defect upstream of model quality. The revised C candidate exposes only those two additional existing tools, without making `native_local_tick`, original-goal amendments, cognitional reopening, memory writes, shell, external access or contract installation model-visible. The client must record two competing option nodes and a CURRENT decision binding the exact compiled action spec, using fresh revision tokens; the existing managed effect gate remains authoritative.

A separate deterministic two-clause control is being checked through real MCP entrypoints, scoped Worker ticks and the independent synthetic compound oracle. It is a **non-model functional control**, not evidence that Qwen2.5 3B can independently create the graph, choose the correct method, execute it or learn it. A successful offline CI will establish only gate reachability; after engineering stability, an explicitly opt-in real-model rerun with the corrected seven-tool surface is required, followed by unseen owner goals before any S2/S5 acceptance claim.

## 6.2. Pre-registered real-model rerun after the managed-gate correction

This is one **opt-in** repeat of the same isolated A/B/C screen at the
unchanged exact original owner goal/fixture/independent-oracle contract, not
a release or architectural selection. The discriminating intervention in C is
the two new already-existing, grant-checked cognition tool capabilities
(`cognition_session_inspect`, `cognition_node_record`) and instructions to
create a CURRENT decision with two competing options before admitting the
matching native local child. The original five-tool C failure remains a
negative control. The 600-second arm ceiling, fixed `qwen2.5:3b` local
model, 18-turn/900-token per-turn C limits, B existing native planner,
harness-only Worker admission, source hashes and independent oracle stay
unchanged.

**Falsifiers and interpretation:** If C still records no decision, examine
tool arguments, actual graph nodes and model/inference budget before assuming
model incapacity. If the graph is current but admission fails, locate the
first failing effect/authority/lineage gate without removing it. If one child
is admitted but not both accepted, diagnose the earliest missing owner clause.
C success on this one synthetic local task is NOT native new-chat selection,
external business result, unseen-domain generalization or S5 reusable method
promotion. B is kept as a failure-prone managed-effect baseline; its current
native planner does not itself record cognitive decision nodes, so B/C do
not constitute a controlled comparison of model intelligence. The experiment
tests *architecture-path reachability* only. Any empirical result must be
recorded against its exact run SHA and retained in full, including errors.

**Opt-in reproducibility fence:** GitHub Actions enables the isolated
`experimental_compound_ab_c` only for a same-repository PR with the exact
`[run-compound-ab-c]` marker in its PR description. A metadata edit alone
must not be treated as experimental execution: confirm a `synchronize`
run on the exact commit after opt-in, confirm the experimental job actually
started (not SKIPPED), and preserve its artifact. If its result is pending,
retain `MODEL_RESULT=NOT_TESTED` instead of borrowing earlier CI success.

## 6.3. Exact seven-tool model result, competing causes, and bounded repair

**Observed RED after §6.2:** GitHub Actions run
[45138814460](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/45138814460)
at exact source head `7d76e50144b6f5d242d4a4b3c8cc7b0b871f9687`
completed its experiment job successfully **as an engineering run**, but the
independent A, B and C verdicts were all `NOT_ACCEPTED`. C ran 11 model
calls, 23 MCP tool calls and 600.175 seconds; it produced zero child tasks.
Its real tool trace repeatedly passed JSON **schema descriptors** (including
`{"title":"Id","type":"string"}`) as `cognition_node_record` parameter
**values**, and hit Pydantic validation errors. The previous five-tool
reachability gap was removed, but no executable method decision was created.
All three original source files remained unchanged. The independent oracle
did **not** accept the task. No actual model ability improvement was proved.

**Competing explanations and discriminators:**

1. Missing legal write path: previously demonstrated and corrected; a
   deterministic client reaches both native methods and the independent
   synthetic local owner oracle through the existing bridge/Host. Not the
   sufficient cause of this latest failure.
2. Complex model-facing contracts: observed failure copies the generic
   `CognitiveNode` schema as call arguments; four sequential node writes each
   required explicit IDs, dependencies, goal version and CAS. Directly supported
   by failed call traces.
3. SDK/Ollama schema translation or local 3B parameter-generation capacity:
   still possible; the trace alone does not assign fault to a particular
   SDK/provider layer. Must be distinguished on the **actual MCP wire** and
   in one controlled real-model rerun.
4. Gate or independent oracle defective: the no-model two-clause positive
   control, original-source preservation and separate independent oracle
   challenge this explanation. No relaxation of a valid gate is allowed.

**Compared routes:** adding more natural-language instructions alone repeats a
previous failed intervention; replacing the model, adding a second autonomous
scheduler or bypassing the gate changes the experiment/authority boundary.
The selected **provisional interface adaptation** projects a single
model-authored choice through a flat `cognition_decision_bundle_record` MCP
tool (five scalar strings) into three canonical nodes under one existing
SQLite transaction. The model still chooses the selected method, competing
option and rationale. The bridge mechanically parses the selected intent,
uses **only already disclosed and digest-verified local source reads**, compiles
the existing action spec, binds a previously inspected revision and lets
`cognitive_session` enforce source/check/commit/rollback/replay. It neither
inventors alternatives nor grants Worker permissions, and the independent
`native_decision_admit` and operator effect contract remain unchanged.
The original generic `cognition_node_record` continues to exist for more
capable clients; only the isolated C tool allowlist changes.

**Independent engineering falsifiers:** in a real MCP stdio schema inspection,
every input field of the compact tool must be `type=string`; the generic
nested node is not visible to C. An injected failure on the third node must
roll back *all* nodes. Missing source-read evidence, wrong owner root, stale
CAS, malformed intent and duplicate options must fail without mutation.
A separate no-model positive control must execute **both** original clauses
and satisfy the unchanged independent compound oracle. Do not call this
a model pass. Cross-platform regressions, artifact source identity and
exact-head CI are required; tests at previous commits do not establish it.

**New real-model discriminator (opt-in after engineering stability):** repeat
the same Qwen2.5 3B A/B/C synthetic owner task and independent oracle, with
original source bytes, registered methods, 600-second bounds, B control,
harness-only Worker and no external effects. C's only functional intervention
is the flat source-pinned atomic cognition interface and its corresponding
instructions; it still has seven allowlisted tools. If the model still copies
schema descriptors as scalar values, return to provider/model/tool-format
diagnosis; if it records a CURRENT decision but native admission fails, inspect
proposal structure and lineage; if it admits only one child, address the
second-clause ownership/review path. **Do not automatically keep repeating
the same expensive screen without a new causal discriminator.**

**Method-learning hold:** this is a domain-neutral *candidate rule*
("mechanical state/CAS/graph construction belongs in a checked tool boundary;
the model supplies semantic options and tradeoffs"). Its applicability remains
`NOT_VALIDATED_FOR_TRANSFER` until an independently checked unfamiliar goal
and an invalidation/rollback probe succeed. Do not promote it into a
general CAOS semantic method or change S0/S5/product readiness on this basis.

## 7. Interpretation rules

- A/B/C results are not selected by model final prose. The independent oracle and actual ledger/artifact bytes determine the local result.
- A failed or incomplete arm is retained as evidence; it is not silently retried or replaced.
- Compare success, clause order, source preservation, lineage, model calls, tokens, tool calls, elapsed time and failure modes.
- One synthetic task cannot select a final CAOS architecture. Any apparent winner must be challenged on the other preregistered task groups: unfamiliar software defect, cross-source research, and method transfer/rollback.
- A green engineering CI is not a product-ready claim.
- No merge, release or deployment is authorized by this experiment.

## 8. Expected artifact

The opt-in GitHub Actions job uploads `compound-ab-c-evidence.json` with all three arms, independent verdicts, bounded tool/decision traces, usage telemetry and explicit non-claims. The job is optional and separately classified by the CI evidence-scope receipt.
