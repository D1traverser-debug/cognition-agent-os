# cognition-agent-os — 总体架构与候选决策（ADR）

## 2026-11-08: challenge the typed-only action architecture before expanding it

The original goal needs unfamiliar tasks and low owner supervision. Current
`capability_catalog` exposes only four registered objectives; `install_contract`
requires an operator-authored exact effect/check document. These are real scoped
protections, but neither is a generic execution solution or a reasonable final
interface for a nontechnical owner. A successful cognitive-node write will not
close this separate architecture gap.

Compare (a) continuing task-specific Worker additions, (b) building another
general shell/execution harness, (c) reusing native Codex execution under an
explicit restricted workspace, and (d) a managed Agents API. Keep (a) as the
existing protected baseline, reject it as the generalization strategy; (b)
duplicates sandbox/process/recovery responsibilities; (d) adds paid-account and
deployment dependencies outside this experiment. Investigate (c) first without
changing production permissions or discarding the existing ledger.

Primary evidence: the [official integration architecture](https://developers.openai.com/blog/codex-as-a-platform)
separates application context/consent from the reusable harness; the
[app-server command/exec contract](https://learn.chatgpt.com/docs/app-server)
exposes a sandboxed argv command without inference. Pinned Codex rust-v0.167.0
`command_exec_processor.rs` blob `1d5c3c7056057512591ff64d952947495176fe75`
applies the requested sandbox through the configured permission constraints and
uses UseDefault execution. `command_exec.rs` blob
`c71aff3ddf22da4958d09351b9d70f05a68d9a4b` rejects streaming/custom output caps
for the Windows restricted-token path. The probe therefore uses buffered calls,
fixed code/argv, native defaults for output caps, no network, and explicitly
excludes broad temporary-directory write allowances.

Strongest counterexamples: a sandbox can reject everything because it is broken;
an error can occur after an unauthorized write; a symlink can escape a path
allowlist; Windows may not have a usable native sandbox. The independent probe
requires a real allowed write and exact byte readback plus rejected read-only,
sibling and (where supported) symlink writes with unchanged protected bytes.
Unavailable symlinks remain NOT_TESTED. This is a public disposable CI opt-in,
not a change to `caos chat`, owner credentials, worker grants or model budgets.
The current Work binary exited before initialization; that is FAIL to establish
this boundary, not proof that sandbox restrictions worked. Exact pinned release
results on Linux and Windows remain pending.

Even a PASS only qualifies a filesystem primitive. Goal fidelity, current-grant
revocation during native execution, evidence isolation, confidential reads,
network effects, unknown ACK recovery and independent semantic acceptance remain
unproved. Do not enable workspace writes in production from this result alone.
If native enforcement fails, compare a genuinely isolated external executor or
retain the narrow baseline; never use an unsandboxed fallback to make it pass.

## 2026-11-07: publish the actual cognitive-node input contract

**Observed retest, 2026-11-08:** `40c04f0` / Actions `42474730960`
FAILED at 900 seconds, 70,085 cumulative native tokens, zero persisted nodes.
Artifact `13615411934`, SHA256
`020abf54074a42f2e84f82fd6e060b94b5a9594195de9c946f16c0e77a3013ed`,
shows all node fields supplied. After a visible stale-dependency rejection the
model removed an invented `goal-0` dependency, but retained an invented absolute
file path for the goal stored in SQLite. Current goal/workspace/task inventory
remained unchanged. This falsifies schema completeness as a sufficient fix for
the record task; it does not falsify the published schema's structural checks.
Investigate provenance affordances and model suitability next: source_refs
refer to real local files, while original goals are ledger values. Do not create
fake files, silently remove references, raise time limits or rerun unchanged
source to call this successful memory/evolution. The execution-boundary probe
below/above is a separate no-inference architecture discriminator.

The `d20c6b8` / Actions `42371600946` retest again FAILED at 900 seconds;
all mandatory checks passed. Artifact `13574622181`, SHA256
`cf2956241fbbf3c3754526bd7178e90f15f329b8969a9f6199b84553b6e6cb1e`,
shows 45,547 cumulative native tokens and no persisted observation. The model
used the actual revision token, received the new missing-field explanation and
added those fields, but invented a string element in source_refs. Thus feedback
did reach the model, while an underspecified nested argument still blocked it.
This is not evidence that the adapter alone completes cognitive persistence.

The same failed model trace also omitted required fields. Runtime recovery
messages are necessary but do not replace a truthful machine-readable interface:
the exposed node parameter was just `dict`, with mandatory fields only in prose.
An actual tools/list assertion reproduced the absent required-field contract.

Use shared TypedDict declarations for the node and its source/method/input/claim
references, consumed by both the existing
core field validator and the MCP schema generator. This keeps ordinary dict
values and all semantic/grant/CAS checks; no second validator authority or
framework dependency enters the stdlib core. The optional MCP environment
already supplies typing_extensions where its schema library needs that backport.
Strict schema configuration rejects unknown fields and scalar coercion instead
of silently deleting or changing caller data. Missing-field guidance comes from
the SDK's anticipated argument-validation error, while domain rejections use
the bounded adapter described below. Real MCP tests verify the published required
fields, incomplete/extra/coerced-input rejection, legal neighboring records and
unchanged ledger after failures. This improves the tool contract; it does not
prove that a model will make sound decisions or transfer knowledge.

## 2026-11-07: distinguish recoverable tool rejection from a private crash

The real additive-record trial at `1a26cd8` / Actions `42347815709` FAILED at
the 900-second deadline, with 55,286 cumulative native tokens. Goal recovery
succeeded; the ledger contained no observation. The actual model submitted
`expected_revision: "0.0"` and omitted required node fields. The result exposed
only `Error executing tool cognition_node_record`. Artifact `13564702806`
(SHA256 `2f7621238b8099c3176f994d65121c50169230c7ea6bf784c20d77e572c19887`)
retains the trace. All mandatory engineering jobs passed; this model trial did not.

Reproducing those arguments through the real MCP 2.3 transport confirms a stale
revision rejection before node validation. Its SDK `tools/base.py` intentionally
masks arbitrary ValueError as UnexpectedToolError; documented ToolError instead
returns an anticipated failure to the model with isError=true. This separates
a correct state guard from a missing feedback path. Do not infer lack of write
permission, automatically fill a fresh CAS token, or claim the narration was a write.

Compare more prompt reminders, globally exposing exception text, and a bounded
transport error adapter. Choose the adapter: map only exact reviewed codes to
static recovery instructions; preserve original checks, isError, grant refusals,
and SDK masking for all unknown failures. No generic retry, authority grant,
input echo, path disclosure or automatic token replacement is introduced.
The same boundary covers missing roots, stale revisions, malformed graph nodes,
changed sources and revoked grants, without changing core APIs.

Actual MCP tests failed before repair, then passed for the observed stale-version
and missing-field cases plus wrong-root recovery. Unknown unsafe-source errors
remain private, and all failed calls leave the graph/revision unchanged. The
same model, original task class, oracle and deadline are retained for one new-source
trial. A failed retest must reopen model/schema/context suitability; green
transport or an assistant promise is not successful cognitive persistence.

## 2026-11-07: additive cognition records are writes, not external execution

First-use source `b79cb83` passed all mandatory jobs in Actions `42347242615`.
Both Windows/Linux real native-client receipts include setup/reuse, cold resume
and unchanged existing ledger. This closes the tested entry-preparation seam,
not owner-device setup or complete goal achievement.

The read-annotation repair exposed the next shared boundary: the native model
also needs to persist investigation and candidate knowledge. Compare leaving
all writes blocked (loses the required memory loop), approving the whole server
(also admits execution prompts), and describing each audited effect accurately.
Choose the third, preserving the single server/ledger and all effect contracts.

The MCP 2025-11-25 `ToolAnnotations` source (blob
`850a083fa228bf40af6feca42e23fd26342d3c59`) defines destructive=false as additive
updates, distinct from readOnly=true. Pinned Codex 0.167.0 Auto mode permits
closed-world additive tools without prompting; Writes/Prompt mode can still ask.
Audit the transitive implementations: hypothesis, input, cognitive-node and
method-trial recording append local events after existing grant/source/revision
checks; records never independently certify truth, authorize effects or delete
history. Give exactly those four readOnly=false/destructive=false/openWorld=false.
Do not generalize from a tool name: `native_open_research_record` can fetch live
GitHub references, so it remains outside this class. Goal changes, decision
admission and Worker execution retain their prior client/server controls.

The actual MCP inventory test failed on the unannotated hypothesis tool, then
passed after the repair, with read-profile exclusion and neighboring effect
tools still guarded. This only verifies the metadata/transport. One new-source
native-model trial requires a real model-originated record and a fresh CLI
process independently reading exactly one observation with the recovered random
marker/constraint. Goal (including amendments), workspace and task inventory
must remain unchanged. False success labels, absent/wrong/duplicate records,
changed goals and invented marker variants fail the oracle. Actual model result
remains OPEN until read back; even PASS would not prove method generalization.

## 2026-11-07: first-use setup reuses the proven entry

Changed-source model test `ba103cf` / Actions `42324264770` passed the real native
MCP/random-marker oracle; all mandatory Windows/Linux checks passed. Artifact
`13555131081` retains the unchanged model digest and actual tool trace. Cumulative
tokens were 43,542 versus the failed attempt's 118,037; this pair is not a general
efficiency benchmark. Full cognition/owner acceptance remains open.

The next usability gap is independently observable: a source download still
requires manual environment, package, native client and state commands before
typing a task. Compare a new browser service/controller, a platform-specific
bundled executable, and a thin cross-platform setup launcher. Choose the launcher
for the current terminal entry: reuse Python venv/pip already used by delivery CI,
the checksum-pinned official-client downloader, and existing init/restore/doctor/
chat commands. This adds no scheduler, goal store or account-login implementation.
Bundled executables remain a candidate if Python installation is a measured barrier;
a web service would not repair missing inference/account access or goal quality.

Setup owns only a marked runtime, verifies cached client identity, isolates Python
search paths, reinstalls changed source and keeps private state outside Git and
outside disposable software. Existing/unowned state is never reset. `--check` is
read-only; setup-only never calls a model. Native CI now runs the actual setup and
reuse with a pinned client and an already-populated goal, then checks the same
MCP/control behavior and unchanged ledger. This must pass on both platforms before
claiming launcher wiring; owner-machine convenience and full product quality are
separate, still-open checks. No one-click claim can remove model login requirements.

## 2026-11-07: validate model-originated permission routing, not only direct RPC

Real inference at `3d196ae` / Actions `42265984438` failed after 900 seconds:
positive model usage (118,037 cumulative tokens), no successful CAOS read and
no recovered marker. All mandatory engineering jobs passed. The retained
artifact `13528556356` shows every attempted CAOS read rejected with
`MCP tool call requires approval, but approval policy is never`. This is not
absence of inference or merely model incapacity: earlier direct native RPC
calls bypassed the model-originated approval route.

Pinned Codex `rust-v0.167.0`, `codex-rs/core/src/mcp_tool_call.rs`,
`requires_mcp_tool_approval` defaults missing hints to possible destructive/open
world action; known read-only, non-destructive tools need no approval in Auto
mode. The CAOS server supplied no annotations. Select truthful read-only,
non-destructive, closed-world annotations for the 12 audited local read tools.
Do not globally approve the server, label writers as reads, weaken source grants,
or swap models to conceal the integration defect. Other client approval policy
may still require explicit approval. Writers remain subject to their existing
client and server controls; this repair does not make them unattended actions.

The real MCP metadata assertion failed on `native_goal_list` before repair and
passed afterward, alongside the existing permission/effect negative cases.
An exact native approval-configuration refusal is now durably identified and
stops the chat invocation; repeating it cannot repair configuration. Unknown
in-flight effects remain unknown, and ordinary correctable tool errors remain
available to the native reasoning loop. A changed-source second local-model
probe uses the same model/case class and oracle to test the permission hypothesis.
Its outcome remains pending until actual readback; passing metadata is not enough.

## 2026-11-07: commit completed replies at their observation boundary

A subprocess counterexample emitted a completed assistant item and then lost
the connection before the turn ended. The previous turn-level write discarded
that useful reply: 1 of 26 focused tests failed. Keeping a larger final buffer
or retrying the model would not correct this durability boundary. Commit each
completed item to the existing event ledger immediately, deduplicate by native
turn/item identity, and let terminal receipts reference those events. A peer
independently reads SQLite before disconnecting, proving persistence precedes
exception handling. All 26 focused cases then passed, including legacy console
encoding. Unfinished streaming deltas remain best-effort display; completed
items are untrusted observations, never verified outcomes or new instructions.

## 2026-11-07: measure the actual native model seam without owner credentials

Native control-only CI proves wiring and cold resume, not inference. Existing
small-model experiments exercised a different fixed-schema Host planner; their
results cannot answer whether the production app-server entry retrieves goals.
Compare (a) repeating those experiments, (b) a metered remote provider, (c) one
bounded, disposable public-CI local-model probe. Choose (c) for this seam only:
reuse the production ChatSession and pinned official Codex, add a session-only
loopback Ollama provider, and observe unmodified native notifications. A random
goal marker exists only in the CAOS ledger; the continuation message omits it.
Acceptance requires a successful real MCP read, a matching final reply, positive
model token usage and unchanged original goal/workspace/task inventory. Record
failed output too. This is a retrieval/inference seam check, not evidence of
architecture reasoning, unseen-task success, owner-device usability or evolution.

Primary evidence: [Ollama Codex integration](https://docs.ollama.com/integrations/codex)
documents Responses wire format and a 64K minimum context recommendation;
[`openai/responses.go` at v0.40.15](https://github.com/ollama/ollama/blob/v0.40.15/openai/responses.go)
implements function-call replay and streaming conversion. The official model
registry lists `qwen3.5:4b-q4_K_M` (Apache-2.0, tools, 3.3 GB), selected to fit
the disposable CPU runner, not as a production quality recommendation. Runtime
and model digest are recorded; the Ollama binary and Codex release are checksum
pinned. Cloud use/web search are disabled. No account config or private goal is
copied. One source-scoped CI attempt, bounded downloads and inference deadline
prevent repeating a failed comparison without a changed hypothesis. Failure
keeps this seam OPEN; no provider fallback or success-shaped fixture is allowed.

## 2026-11-07: preserve native history and accounting on explicit resume

The bounded native loop still started a new native thread for each invocation.
CAOS could recover original inputs, but this needlessly discarded native working
context and created new budget accounting. Reuse `thread/read`, `thread/goal/get`
and `thread/resume`, not a second conversation store or replay of earlier turns.
An explicit `--resume-client [THREAD_ID]` requires a clean terminal delivery
record bound to the selected CAOS root, then checks actual native identity,
workspace, objective, quiescence and spent tokens. Multiple candidates are not
resolved by recency. Missing/moved/wrong/unknown state fails without creating a
replacement thread. Persist new input before native access, record dispatch
before resume, and preserve native creation time and usage when changing the
explicit total budget without an objective replacement.

Alternative review included the official Python SDK at `rust-v0.167.0`:
`sdk/python/src/openai_codex/client.py` blob
`5b38538c541aa17e807aecfa3d5a58c9ee76d0ff`, `_goal.py` blob
`37a63fc28f4c618a4dbc77e9e408e3f4a7ae24b4`, and `pyproject.toml` blob
`3d920e43d21448ce081b4dd68a93f11fd66da4b3`. It is a serious future replacement
candidate, with existing goal-event routing and typed protocol support. At this
revision synchronous response/notification waits have no per-call deadline,
stdout uses unbounded `readline`, the simple goal setter lacks budget/origin
arguments, and packaging pins a different CLI runtime (0.153.4). A drop-in
migration would still need boundary adapters and actual version validation;
retain the tested bounded transport for now, not a claim of universal superiority.
Reopen this choice if measured maintenance or compatible SDK behavior favors it.

Falsifiers include preserved nonzero usage across separate protocol processes,
exhausted total budget, wrong workspace/root, ambiguous threads and unknown
dispatch. The pinned native CI probe also reopens the same paused thread in a
new process, verifies unchanged creation/usage, and changes only its explicit
total budget without inference. Real model recovery and reduction in owner
corrections remain open; no private account or production outcome is inferred.

## 2026-11-06: reuse native goal continuation instead of a second loop

`5f1ccc8` native transport jobs on Linux and Windows (run `42197902683`)
successfully used official Codex 0.167.0 to discover 23 CAOS tools, read the
original goal, and reject a missing required server. This is real wiring;
no inference or owner-account acceptance was performed.

The next architectural counterexample is lifecycle: the initial chat adapter
uses ephemeral threads and stops at `turn/completed`. Official app-server
documentation and release `rust-v0.167.0`'s
[`thread_goal_processor.rs`](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/app-server/src/request_processors/thread_goal_processor.rs)
(blob `82aeaf7f46f92244e59279012bc1033934fbe25a`) explicitly reject goals on
ephemeral threads; activating a goal can itself start inference. A second
Python retry/scheduling loop would duplicate native continuation and risk
double dispatch. Merely adding a continuation prompt cannot fix this lifecycle.

Choose opt-in `chat --goal-budget N`: use one native persistent thread and its
existing goal engine for a bounded invocation; ordinary chat remains ephemeral.
Prepare the native goal PAUSED, persist original input and dispatch intent,
then activate it once (never also call `turn/start`). Keep listening across
completed native turns until goal pause/block/budget/usage/completion or timeout.
Use native accounting plus the existing wall-clock deadline, not a new queue.
Goal objectives have a 4,000-character limit: bind a stable root locator rather
than truncate or replace the full original, amendments and inputs in CAOS.
Reject native objective/budget replacement. Native completion still cannot
set the CAOS independent outcome to true.

Each explicit invocation has its own requested budget; no automatic restart,
background service, account configuration edit or transparent budget reset.
Native conversation/goal state is kept by the native client in its normal local
storage; CAOS delivery events retain the thread ID. A failed/unknown dispatch
requires effect inspection before another invocation. Timeout/close requests a
native pause when possible; process exit is not proof of cancellation/rollback.
Same-process invocation reuse is rejected. At this initial checkpoint,
cross-process native-thread resume was unimplemented (superseded by the explicit
resume decision above). Actual model-driven goal continuation remains unverified;
retrying the saved owner message is not its implementation.

Protocol-peer counterexamples cover two completed turns before native completion,
late paused notifications, budget exhaustion, missing ACK, timeout/pause,
unexpected existing goal, cleared goal and objective drift. The real native CI
probe additionally prepares and rereads a paused goal with zero tokens used;
this validates the control path without calling a provider. Native-loop outcome
quality, cost reduction and cross-task learning require separate real inference
and independent result evidence. Rollback: omit the goal option while retaining
the owner ledger, input and delivery history.

## 2026-11-06: make input persistence an entry responsibility

The preceding launcher proves MCP preparation/transport, but hands subsequent
messages straight to the native UI. Saving every correction therefore still
depends on the model remembering a tool call. This is a missing observation
boundary; adding another instruction cannot make omitted input durable.

Compared: retain the TUI (least code, no deterministic input capture); rebuild
a standalone model/tool runtime (duplicates permissions, scheduling and recovery);
adapt Codex app-server (adds a protocol adapter while retaining its harness).
Choose the adapter for an opt-in `caos chat` entry, keeping `launch` available.
No browser service, account config edit, second database, scheduler or automatic
model-retry loop is introduced. The first plain-text message can create a goal;
existing goals are discovered and ambiguous choices remain explicit.

Official [app-server protocol](https://learn.chatgpt.com/docs/app-server) and
the installed 0.167.0-alpha.4 generated schemas were checked for initialization,
thread/turn startup and approval replies. Actual upstream `turn_admission.rs`
(blob `552875473b9929a02317a892f0e7d02d9a7dfe7a`) and its tests
(`d36f15eea6de0b274ffb39410c2c46b39db5bf4e`) demonstrate shutdown admission
tracking, not exactly-once business effects. `transport.rs`
(`4aef6998354c67a009b113f8103a83fdacea1e8b`) can drop messages for disconnected
clients. Thus a missing ACK must remain UNKNOWN, not trigger automatic replay.

User messages and clarification answers are committed to the existing ledger
before forwarding. Delivery markers, questions and untrusted assistant replies
also use existing events; metadata-first paginated readback avoids rereading
every reply. The existing later-input fence now sees input before inference.
Native shell policy is read-only with escalation denied; CAOS MCP contracts
remain responsible for admitted effects. This does not fence every other
connector the operator may have configured. No model reply promotes a method,
changes the goal or certifies an owner outcome by itself.

Falsifiers: process failure before delivery, lost ACK, early/out-of-thread
completion, replay, clarification EOF, conflicting goals and cold source-gated
MCP readback. Real subprocess protocol-peer tests cover these transport facts;
they are explicitly not a model evaluation. The real installed Codex app-server
currently exits during startup because its Work runtime home is read-only.
An isolated SQLite-directory override did not resolve the remaining read-only
startup failure. No account configuration/credentials were rewritten. The
adapter's native successful inference, full semantic workflow, correction burden
and cross-task learning remain NOT_TESTED. Roll back the adapter independently
while retaining saved inputs and delivery evidence; never automatically resend
an unknown delivery or discard original messages.

The first exact-head cross-platform run (`ad123ed`, run `42165581798`)
passed Linux but failed three Windows protocol-peer tests involving Chinese
input. A `PYTHONIOENCODING=cp1252` reproduction failed before the peer's delivery
marker; explicitly setting the peer's stdin/stdout to protocol UTF-8 makes all
12 tests pass under that same setting. Production already uses UTF-8. Keep the
Chinese fixtures; this correction does not establish native-client integration.
To discriminate client incompatibility from Work's read-only runtime, the
existing disposable Windows/Linux transport jobs now also start checksum-pinned
official Codex `rust-v0.167.0`, read back a real CAOS goal through its MCP client,
and require a broken mandatory MCP server to reject thread startup. No model
turn or owner account is used. Its receipt separates wiring from inference and
owner-outcome acceptance; native success is pending actual execution.

## 2026-11-06: preflight the actual installed transport

The first CI run exposed a Linux user-site installation failure: the actual
artifact log showed `ModuleNotFoundError: mcp` under `-I`, while Windows passed.
Use `-E -P` instead: retain normal user/system dependency directories while
excluding environment overrides and unsafe working-directory insertion. This
is a compatibility correction based on the failed real transport, not a
waiver of the connection test.



Windows CI on fb17a89 failed because the launcher test created a directory
containing quotes, which Windows forbids. The portable fixture now retains
spaces, Unicode and shell metacharacters without using an illegal filename.
Inspection also found that preparation alone did not prove a working server:
the MCP SDK can discard PYTHONPATH and load an older wheel from the same Python.
Bind startup to the current package path with controlled Python startup and an argv-only
bootstrap. The production --check now performs real MCP discovery and a
read-only state call; it has a bounded timeout and omits private text from its
receipt. The existing cross-platform MCP integration exercises this exact
path and checks event-count invariance. No model/provider, account setting,
permission, scheduler or second state store is added. Native model invocation
and owner-outcome acceptance remain separate obligations.

## 2026-11-06: executable native-client entry, conditional integration

The package had an MCP server and instructions but no executable client entry.
Choose a session-scoped local Codex launcher first: it reuses the existing
model/tool runtime and the same private ledger without another server, queue,
state authority or model subscription. A standalone web application introduces
another runtime before the current model/action boundary has been verified;
OpenCode/WorkBuddy remain replacement candidates if real client results favor
them. This is a bounded integration choice, not evidence of an optimal whole
architecture or a completed cognition system.

The launcher validates state/root/client/dependency, passes argv without a shell,
requires its MCP connection, propagates native failure and never edits account
configuration. It inherits native policy and does not claim to intercept other
tools. Explicit preparation was exercised against the private active session;
path quoting, missing dependencies, wrong root and failure propagation are
tested. Authentication and native model outcomes remain unverified: a fresh
45-second no-tool probe with closed stdin still times out and reports a plugin
catalogue 401. No credentials were read or rewritten. Do not infer a model
endpoint diagnosis from that plugin error, and do not call --check a connection.

## 2026-11-06: new input invalidates an older action decision

Real MCP reproduction showed that a new user message arriving after action
admission left the old decision admissible. Prompt-only routing and relying on
the user to call reopen do not cover that path. A new queue/controller would
duplicate the existing ledger. Reuse the shared admission and effect-time
guard: any uninterpreted input, or input newer than the current decision,
requires a fresh decision. The existing action-binding identity prevents an old
queued action silently inheriting a new decision. This is conservative: benign
late messages also pause work. A new decision must follow the input; merely
recording an interpretation cannot revive the old decision.

The MCP integration probe exercises late input, interpretation without a new
decision, and a new decision alongside a pre-existing authorized positive case.
This is an ordering invariant, not proof of semantic understanding: a model
can still record an incorrect new decision. Nor does it interrupt an effect
already in flight or govern client tools outside this ledger. Full outcome,
native client integration and cross-domain evaluation remain open.

## 2026-11-05: recover cognitive state through the existing client entry

After the public-boundary commit's CI passed, a direct read of the real private
session through `codex_session_context.py` still returned only the original
goal/legacy decision state: no cognitive corrections, input counts or graph
revision. Two fresh-process tests reproduced the omission for a single root
and competing roots before implementation. Storage existed, but the entry's
read path did not expose it. A successful SQLite snapshot alone therefore did
not establish complete conversational recovery.

Alternatives: more intake wording cannot reveal omitted state; a separate hook
cache duplicates identity and becomes stale; replacing the entire store loses
tested lineage without addressing the missing reader. Reuse the existing
`cognitive_session._project` in the existing continuity snapshot instead. Root
identity remains unchanged; original goals and corrections stay distinct.
Automatic hook output carries only counts/version/locators. Explicit readback
recovers corrections and pages nodes/messages with the same revision token.
Changed source bytes, corrections and input-only updates reject old locators;
multiple roots retain separate amendments and no automatic selection. No
execution grant, second queue, account setting or Skill is added.

Acceptance: real Python subprocesses, raw-private-text non-disclosure in startup
output, exact correction/message recovery, multi-root separation, paginated
messages, source invalidation and stale locator rejection. These prove the
reader wiring, not actual native client invocation or semantic understanding.
The next unresolved client test must observe invocation in a supported client.

Official platform evidence was also checked directly: [MCP](https://learn.chatgpt.com/docs/extend/mcp)
and [Plugins](https://learn.chatgpt.com/docs/plugins) state that cloud-orchestrated
Work does not support local/plugin command hooks; local Codex config does not
connect ChatGPT web. [Packaging](https://developers.openai.com/plugins/build/plugins)
describes local plugin hook resources/trust, but is not account installation
evidence. Use supported local Codex entry when available, or explicit scoped
CLI readback in this Work environment. Do not promise a cloud hook by packaging
local scripts. Remote service/account integration remains a distinct boundary.

## 2026-11-05: one public execution boundary and reproducible delivery evidence

The full parent goal and download-and-use requirement remain OPEN. Reviewing
the original forbidden-goal probe against the current source still produced
five forbidden local effects through the unmanaged low-level research API.
Tracing the same path found that MCP `allow_goal_writes` exposed admission
without requiring a managed root. The shared cause is incompatible public
entry profiles: recording a goal could implicitly expose legacy execution.

Considered routes: a natural-language keyword filter misses paraphrases and
legitimate neighbors; disabling every effect falsely passes denial tests while
breaking useful work; rewriting the entire ledger breaks tested recovery and
does not establish semantic understanding. Selected: reuse the existing
managed root, contract and transactional effect guard for ALL public MCP effect
entries. New CLI/MCP goal registration and its managed marker commit atomically.
Legacy reads remain available, but admission, tick and local-model paths reject
unmanaged roots. An unused keyed root may be restricted without changing ID;
a root with existing children cannot be silently adopted. Low-level Python
compatibility remains explicit and is not a safe agent-facing execution profile.

Countertests cover rollback on registration failure, keyed retries, pending
legacy work, rejection before each effect call, missing-contract denial and
real authorized positive effects through official MCP subprocesses. Operator
fixture contracts are outside MCP and do not masquerade as model-derived user
authorization. This closes a reachable execution bypass, NOT the arbitrary
natural-language interpretation problem or shell/SQL/other-connector authority.
Rollback must retain managed enforcement; using an older runtime on this state
is not a safe rollback.

Repeated manual checks also hid evidence scope and consumed context. Reuse the
existing probes through `verify_delivery.py`: no new evaluator/controller or
test database, no network/model call. Its receipt binds source content and log
hashes, runs installed-wheel acceptance in isolation, and reports each profile
separately. The same transport command runs in CI on both OSes. Existing
`plan_incremental_audit.py` handles structural deltas. Neither source hashes nor
test orchestration can certify cognitive quality. Unseen model tasks, native
entry traces, correction burden, method transfer and independent owner outcomes
still determine product readiness; passing this receipt cannot authorize merge
or a ready-for-use claim by itself.

## 2026-11-05: external research enters as evidence, not replacement authority

Scope: continue the complete parent product below. New research does not reset
the project, install a new System Prompt, or select a framework by popularity.

### Findings and competing causes

- **Missing instruction alone is not an adequate explanation.** Existing AGENTS
  and the installed intake already distinguish goals, research and effects.
  More wording does not demonstrate that the client selected or obeyed it.
- **Input/interpretation lifecycle is incomplete.** Before this change the
  cognitive API retained amendments and derived nodes, but no separate raw
  conversation input. `amend_goal` deliberately invalidates every prior node
  and effect contract. Sending a suggestion/research bundle there therefore
  changes goal identity and invalidates unrelated work. Sending it only as a
  hypothesis loses its distinct provenance and tentative intent categories.
- **Activation and semantic quality remain separate open causes.** Persisting a
  message cannot prove the model understood it, read every constraint, selected
  the best architecture, or used the entry in a fresh ordinary conversation.
  The original forbidden-proposal baseline remains relevant; this change is
  not a general natural-language authorization fix.
- **Read permissions need to cover derived copies.** Cognitive graph nodes can
  contain source quotes. Their MCP reader previously omitted `allow_source_read`.
  The input and graph readers now both enforce that existing disclosure setting.

### Actual external mechanisms inspected

| Source and observed blob | Applicable mechanism | Counterexample / transfer boundary |
| --- | --- | --- |
| [GSD execution](https://github.com/open-gsd/gsd-core/blob/main/gsd-core/workflows/execute-phase.md), `72722e6eb4853f76c7e76feb3eda2f4b92b6a337`; [verifier](https://github.com/open-gsd/gsd-core/blob/main/agents/gsd-verifier.md), `860c6f833806441adb51c70dd1df2ba3c69a9dc1` | Resume reconciles reachable commits with summaries; outcome requirements cannot shrink to plan tasks; behavior-dependent claims need runtime evidence | Workflow instructions are not a native CAOS hook. Initial compiled-path 404s were traced to build-at-publish sources: [verification.cts](https://github.com/open-gsd/gsd-core/blob/93bb3b283998b5845cd94be98c9ce240d2946c12/src/verification.cts), blob `b71b6ccdd00b3f26a00943b16f04a0ecfdc04e0b`, and [verify.cts](https://github.com/open-gsd/gsd-core/blob/93bb3b283998b5845cd94be98c9ce240d2946c12/src/verify.cts), blob `6589ed669a13e90cbe003b58af523701b754b0de`. Actual readers distinguish missing/unreadable evidence and recheck declared content fingerprints; legacy reports can use timestamp fallback. Those mechanisms still cannot prove an agent-written passed verdict is semantically correct. Source reviewed, upstream runtime not executed. |
| [Atlas hook](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/packages/omo-opencode/src/hooks/atlas/atlas-hook.ts), `6e7969ccfaf0020f0047a169fbbc33ba30ef6701`; [idle handler](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/packages/omo-opencode/src/hooks/atlas/idle-event.ts), `72a86bc0cfa4d7bbb9dda3f1363f3e493d10fe46`; [continuation](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/packages/omo-opencode/src/hooks/atlas/idle-continuation.ts), `850dc94020159da35cf37b84c72dc20126547e1b` | Runtime events, active-session identity, no-progress detection, cooldown, bounded retries, stop and background-task checks | Depends on OpenCode PluginInput/session events and continuation injection. It is not portable by copying its prompt into ChatGPT. Counted tasks and tool activity still do not establish owner-goal achievement. No runtime installation or efficacy trial performed here. |
| [prompts.chat schema](https://github.com/f/prompts.chat/blob/main/prisma/schema.prisma), `97f36369649ad5c4565df2c9673274bb3d2b4fc6`; [team changes](https://github.com/f/prompts.chat/blob/main/src/lib/bots/team-changes.ts), `6482330766f5e6a95d7cf9acccfb5920f7bf082b` | Stable assets, separate proposed/original snapshots, versioned application, reviewer permissions, preservation of members hidden from a proposer | The inspected approval function applies the proposed snapshot; it does not itself compare the saved original with live state. Version history alone cannot prove conflict safety or effectiveness. Reuse CAOS CAS/dependency invalidation rather than importing this application/database. |
| [ReAct original paper](https://arxiv.org/abs/2210.03629), v3; [GraphPrompt original paper](https://arxiv.org/abs/2302.08043), v3, followed from Prompt Engineering Guide | ReAct interleaves information-gathering actions with revisable planning; task-specific method choice | GraphPrompt is a GNN pretraining/downstream-task method, not an Agent Workflow Graph implementation. Neither paper proves CAOS's current client, intent recovery or authorization. |

Third-party leaked prompt collections are unverified implementation references,
not official runtime contracts. No copied leak, new dependency, new Agent or
automatic core-rule update is introduced. This review does not certify a current
top-ten Stars ranking or claim all ten repositories were exhaustively executed.

### Alternatives and second challenge

| Route | Coverage/reliability | Complexity, cost and compatibility | Failure mode / choice |
| --- | --- | --- | --- |
| Keep only chat/Skill wording | No durable distinction between new material and goal changes | Lowest code change, repeated recovery/correction burden | Reject as sole solution: same failure remains after interruption |
| Separate intent agent plus vector store/controller | Could improve retrieval/interpretation with measured model evaluation | New model calls, identity/store synchronization and migration; still needs existing grants and outcomes | Defer: no measured accuracy benefit; another agent can misclassify the same message |
| Replace the stack with GSD/OmO | Useful supported-client coordination and recovery mechanisms | Different clients/state conventions; significant migration and activation work | Not justified by these input-lifecycle failures; client comparison remains open |
| Extend existing event ledger and dependency nodes | Exact raw input, tentative interpretations, CAS, supersession and cold recovery | No new service/table/scheduler/dependency; testable via current CLI/MCP | Selected for this boundary, not asserted globally optimal or semantically sufficient |

Strong counterexamples: a quoted instruction can call itself an owner goal; a
model can confidently misread a suggestion; a later correction can invalidate
an earlier interpretation; two readings can disagree; an input may arrive after
an action is queued. Accordingly, origin is explicitly unauthenticated, every
reading remains unverified, category labels never amend goals/grant effects,
competing readings stay visible, and amended/reopened/superseded readings use
the existing dependency invalidation. Raw inputs survive these changes.

Implementation uses `COGNITION_INPUT` events and `interpretation` nodes in the
same root/ledger. Claims quote exact input bytes and distinguish explicit,
inferred and uncertain readings. Graph readback reports counts; raw input is
paged separately. Rollback is a forward correction/reopen, preserving originals;
do not run an older binary against a snapshot containing unfamiliar node kinds.

Acceptance covers input retention, unchanged goal identity, false-quote and
false-confirmation rejection, dependent-plan invalidation, competing readings,
idempotency/CAS, actual MCP subprocess recovery and installed CLI snapshot
roundtrip. It does NOT certify NLP accuracy or independent semantic review.
Uninterpreted counts are advisory: receiving a message alone does not cancel an
already-authorized task. The caller must apply a genuine correction/reopen and
link decision dependencies; the current tools cannot authenticate owner intent
or intercept unrelated connectors. Automatic correct routing, held-out model
evaluation, native client activation and cross-domain transfer remain OPEN.

## Product architecture correction: cognition before Host mechanics

The complete product is an opt-in interactive parent that can investigate and
solve its own failures, then guide independent child systems. The managed
ledger/Worker experiment below covers only part of this product. Its green CI
does not validate the calling model's investigation, research, architectural
judgment or sustained execution. Do not keep selecting easy Host defects while
these parent-level outcomes remain untested.

### One parent with distinct responsibilities

| Component | Required behavior | Evidence needed before calling it working |
| --- | --- | --- |
| Entry and goal recovery | On an explicit wake, identify the selected project, recover original requirements/corrections, current state and grants; avoid unrelated chats | Actual related/unrelated client traces, cold and interrupted resumes, full-clause fidelity |
| Cognitive decision loop | Challenge the symptom, diagnosis, research strategy and proposed fix; reopen earlier assumptions when new evidence contradicts them | Competing causal explanations distinguished by observations, including failure of the chosen explanation |
| Research and solution design | Discover materially different approaches; study primary implementations, tests and failures; compare adaptation, consolidation, replacement and reconstruction | Versioned source/experiment receipts tied to unresolved questions; design comparison and a second challenge before execution |
| Working context and knowledge | Keep raw authority, task state, evidence claims and reusable procedures distinct; retrieve only needed detail | Original clauses survive compression; source conflicts are visible; changed evidence withdraws dependent advice |
| Controlled execution and result | Bind the chosen goal/method/action to lawful tools and independently read the meaningful outcome | Legal/forbidden/prerequisite neighbors, interruption reconciliation and genuine domain validators |
| Method evolution and child interface | Derive scoped methods from results, test transfer and regressions, promote or roll back versions; guide child work without taking its business authority | Held-out tasks and negative transfer controls; child-native result readback and fewer owner corrections |

The calling ChatGPT/Codex model remains the reasoning actor. The existing private
Skill is guidance, not an enforced loop or account-wide hook. GitHub, private
files and optional Host state must expose current facts to that actor; no one
surface may silently substitute its summary for the original goal. A supported
controlled client can enforce its own tool/stop boundaries; the present ChatGPT
surface cannot claim interception of every other connector's operation.

### Nonlinear control and stop semantics

Diagnosis is provisional, not a single question followed by a patch. A knowledge
gap opens research. Research may disprove the diagnosis or reveal a missing
requirement. Competing designs must be compared under relevant owner tasks and
lifetime maintenance cost, including reconstruction when its long-term result
is better. Before acting, challenge the preferred design and its assumptions
again. Execution failure may reopen requirements, evidence, method, architecture
or the validator itself. Preserve independent branches that remain legitimate.

Research depth is established by resolving material uncertainty with source
and experimental evidence, not by counting links, reflection rounds or model
statements. Several genuinely different candidates must be studied for an
uncertain consequential design; that is not a rule to fetch three arbitrary
README files on every task. Budget exhaustion yields incomplete research with
explicit remaining uncertainty, never successful research by default.

There are separate decisions to stop a tool attempt, suspend an unresolved
investigation, accept an implementation, and declare the whole owner goal met.
The last requires the complete outcome and its independent evidence. A local
test or a completed method card cannot authorize that transition. Current
ordinary chat cannot guarantee automatic continuation after a final answer;
this is a platform boundary to test with supported client integration, not a
reason to defer other interactive work to a future always-on server.

### Reuse research; do not restart the bibliography

The existing source atlas and research cards already study many Hub projects.
Live rechecks found identical Open Deep Research and SkillOpt blobs below;
retain those conclusions rather than claiming another novel full study.

| Actual source inspected | Mechanism worth adapting | Strongest limitation for CAOS |
| --- | --- | --- |
| Open Deep Research `deep_researcher.py`, blob `279dbffd9e49e07962fb4e1cfeff79e45adc43e9` | Research brief, follow-up tool loop, raw notes retained alongside compression | Supervisor can stop on no tools, completion signal or iteration limit; that is not independent proof of sufficient research |
| STORM `knowledge_curation.py`, blob `d6b892957e5ef2c68d659c294bf64a02c9135b2e` | Perspective-guided question generation and retrieved source conversations | Bounded conversation and model answers do not establish an engineering root cause or permitted business effect |
| SkillOpt `docs/guide/training-loop.md`, blob `3ba0d524d36a5dc4774f918931d22732670e4006` | Trajectories, candidate aggregation, controlled edits, selection validation and regression comparison | Ungated configurations can force acceptance; a validation improvement is scoped to its evaluator/data |
| Hello-Agents `Extra-Chapter/Extra10-Agent自进化.md`, blob `07dcc30d07d6508ab55a290dc135f916148a0a9e` | Separate context, skill, shared-experience and strategy/code evolution loops | Tutorial mechanisms do not prove runtime activation, transfer or permission in the present client |

Sources: [research loop](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py),
[questioning implementation](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/knowledge_curation.py),
[evolution gate](https://github.com/microsoft/SkillOpt/blob/main/docs/guide/training-loop.md),
[four evolution loops](https://github.com/datawhalechina/hello-agents/blob/main/Extra-Chapter/Extra10-Agent%E8%87%AA%E8%BF%9B%E5%8C%96.md).

### Consolidation and acceptance direction

Retain reliable transaction/effect/recovery components as optional supporting
infrastructure. Do not equate their typed action catalog with general cognition.
Keep research/knowledge provenance and actual result evaluators; consolidate
overlapping interface responsibilities only after checking their distinct
contracts. Do not add another scheduler or a permanent repository-wide prompt.

The next product comparison is the actual interactive parent versus the managed
client path on equal tasks: an unfamiliar architecture problem requiring deep
research, an interrupted task with a late correction, a misleading-source or
invalid-experience case, and an independently governed child task. Observe
missed clauses, unsupported claims, wrong effects, recovery, owner interventions,
tool/context cost and final outcomes. No model trials, deployment, native fresh
chat trace or child-business result is fabricated by this architectural revision.
The entire product remains NOT_READY; the correction is not a release gate pass.

## 2026-11-04: executable managed session experiment (conditional)

The live integration baseline `cc22304c6ebae884aae95efbc19874e6b018498a`
passes 1,179 standard-library tests, while the supplied owner-alignment probe
still permits and executes all five explicitly forbidden proposals. Seven
operational interfaces also create empty databases when invoked without a
provisioned ledger. Reproduced locally before changing code. These observations
separate semantic admission, operational provisioning and actual client
connectivity; they do not justify blaming every failure on one cause.

| Alternative | What it changes | Counterevidence / decision |
| --- | --- | --- |
| More Skill prose | Model guidance | Detailed rules already coexist with false admissions; no enforcement improvement demonstrated. |
| Replace all state/execution with a graph SDK | Scheduling, checkpointing, interruption | Upstream mechanisms still require application-specific guards and outcomes. No measured semantic advantage or migration justification. |
| Keep existing ledger/Worker, add executable evidence dependencies and operator-bound effects | Actual admission/write boundary, recovery and source invalidation | Selected as a bounded experiment. Cannot infer arbitrary owner intent or control unrelated connectors. |
| Deny every unknown goal | Avoid effects | Prevents legitimate exploration; managed research/observations stay available while unbound effects are rejected. |

First-hand code inspected: LangGraph `pregel/_loop.py` blob
`579b8ae09d074e7aaabf6e643cc5fe554a1cdbc6` (`tick`, `_suppress_interrupt`),
OpenAI Agents `tool_guardrails.py` blob `613d5dbcecb4bb0e71169e9f2cf81d331023473b`
(allow/reject/raise behaviors), AutoGen `_base_group_chat.py` blob
`60f222912387d37be37f457ad486d51060255966` (`save_state`, `load_state`, consistency
warning during live runs). These implementations establish useful mechanisms,
not a product superiority benchmark. No upstream code is copied into runtime.

Source URLs:
- https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/pregel/_loop.py
- https://github.com/openai/openai-agents-python/blob/main/src/agents/tool_guardrails.py
- https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat.py
- https://learn.chatgpt.com/docs/extend/mcp

Implementation: reuse native goal identity and the same event ledger; append
immutable corrections/nodes and derive source/dependency status at read time.
An operator contract is separate from model records and unavailable as an MCP
grant tool. Admission and artifact-write guards both enforce it. Restored
snapshots preserve IDs but require fresh operator binding. Legacy typed roots
retain compatibility and are explicitly not covered by the new semantic policy.

Falsifiers: stale source or reopened ancestor still executes; legal bound
neighbor is blocked; source text can mint authority; cold recovery loses a
correction; restored grants silently reactivate; method outcome changes without
withdrawal. Real SQLite/Worker and official MCP subprocess tests exercise these
conditions. A whole-framework replacement can be reopened if comparable native
model trials demonstrate better owner outcomes/maintenance cost. Those trials
have **not** been run; no claim of optimal architecture or product completion.

Original M033 arbitrary-language understanding remains OPEN. Manually supplied
operator policies are not evidence of automatic goal comprehension. This branch
must not merge under the complete-product delegation until outstanding product
gates and independent review are resolved. Operational entry and rollback:
[`PRODUCT_OPERATION_AND_ACCEPTANCE.md`](PRODUCT_OPERATION_AND_ACCEPTANCE.md).


> 状态：**DESIGN PROPOSAL / 未冻结** · 2026-10-20 · 对应 [00-PRODUCT-CONOPS.md](00-PRODUCT-CONOPS.md)。任何技术名称都是备选方案，不得误写成已经部署。

## A. 系统约束优先于框架

本系统的真实产品是**有目标约束、有证据、自主持续推进并能治理自身失效的完整控制系统**，不是一个聊天前端、不受控 LLM 循环，也不是多 Agent 角色集合。先定义权威与不变量，再评估模型编排、任务引擎和宿主。

不可绕过的不变量：

- I-01 目标与授权来自可信主责，不因 LLM 推理、工具描述或检索内容自行提升权限。
- I-02 每项可变事实有明确逻辑写权威；观察副本允许多个，不能各自认定最终真相。
- I-03 每次有副作用的动作在真正执行入口重新检查**当前**授权、目标版本、依赖知识、预算和操作身份；承认远端在途撤权仍有供应商特定风险。
- I-04 持久任务状态与模型对话会话、MCP 会话、HTTP 请求 ID 相互独立；崩溃后能恢复合法工作。
- I-05 UNKNOWN 不是 FAILED；不可重复提交未知结果的远端业务意图，除非有明确幂等/对账合同。
- I-06 任务自述或 CI 绿色不等于用户结果；独立证据源判定有真实效果。
- I-07 自主治理必须从发现走到系统性修复与复发检查；自生成的候选不得自我认证后晋升。
- I-08 授权的合法剩余工作不应因其他任务受阻而全部停滞；必须管理容量和费用。

## B. 候选逻辑架构

```text
外部可信输入 / 用户目标 / Host 事件
             │
    ┌────────▼────────────┐
    │ Control / Authority │ ←目标版本、授权引用、持久任务、预算、事件审计
    └──┬──────┬──────────┘
       │      │
       │      └─> Evidence/Knowledge Store ←版本化来源、依赖、争议与撤回
       ▼
 Decision Engine [LLM / code policy] —> 有限、结构化 Plan/Action Proposal
       │                                  （没有写入权）
       ▼
 Admission + Scheduler [可信代码：当前版本/预算/租约/资源]
       │
       ▼
 Execution Gateway [统一写入口、身份/作用域/参数指纹/操作日志]
       │
       ├── Local Isolated Workspace / Files
       └── Provider Adapter [未来沙箱或外部写入，契约明确才开放]
                     │
       Independent Read-back / Outcome Evaluator
                     │
           Task/Knowledge/Goal Feedback
                     │
  Diagnostics → Failure-class scope → Candidate → Independent eval
                          → Authorized promotion / Hold / Rollback
```

逻辑模块不等于独立微服务。P1 可以让多个模块共享进程与数据库，但必须有可替换接口和执行网关；外部执行和模型进程是否隔离留给实测。

## C. ADR 表：本轮拟议、适用条件、反证

| ADR | 候选默认 | 适用/验证条件 | 可以推翻它的证据 |
|---|---|---|---|
| 01 宿主触发 | 单机真实定时/事件 + 持久扫描作为可逆 P1 基线 | 独立真实唤醒，记录 missed tick，重启恢复 | 目标环境无法持续在线、需要托管触发或跨天等待 |
| 02 服务拓扑 | **对比**模块化单体 M 与核心权威+隔离执行器 H，不预先选 D 微服务 | 六类事实 owner 清楚，故障/性能/运维成本可测 | 故障隔离、租户安全、负载明确需 D 或托管方案 |
| 03 智能规划 | 先以单 Agent + 明确结构化 proposal 作为成本/正确性基线 | 与代码规则、模型版本、预算和负例对照 | 多 Agent 在同预算同目标中稳定提高独立验收成功率 |
| 04 工作流引擎 | 起点关系型任务台账+版本转换+outbox；与 Temporal/托管 workflow 对比 | crash/ACK loss/版本升级的同场景真实故障测试 | 自管任务引擎复杂性或长任务需求压倒其优势 |
| 05 授权入口 | 一切有副作用的适配器穿过可信执行网关 | SDK、handoff、hosted、shell、scheduled 等入口逐一审计 | 有任一绕过时禁止该写入通道，需重新封装/下沉权限 |
| 06 知识系统 | 证据与派生结论分层、维护来源/版本/依赖 | 修改证据能使受影响任务失效、无关任务保留 | 结构化成本过高、实际迁移无益则简化 |
| 07 远端效果 | 意图 ID + 参数指纹 + UNKNOWN 对账，不许盲目重试 | 首个 provider 的幂等时限、查询 API、撤权时点经核对 | provider 不具安全合同则只读/隔离，无资格进入真实写入 |
| 08 独立验收 | 业务 owner/外部真相 + 版本化 evaluator，轨迹只作辅助 | 开发集与隐藏集分开；版本、成本、纠错负担可审计 | oracle 被证明错误时结果 INVALID/UNKNOWN，不“自证通过” |
| 09 自主治理 | 现有工作流内闭环：发现、根因、范围、候选、独立证据、晋升 | 修复跨 sibling 入口及相邻合法动作的回归测试 | 自我评估可伪造或候选影响不可界定则不得晋升 |
| 10 资源调度 | 全局预算保留 + 资源计量 + 公平队列/背压 | 高优任务突发时普通任务仍有正当进展 | 任务成本与数量异质时需按真实资源权重重调 |
| 11 版本与退出 | 目标/知识/模型/执行器/数据 schema/评测分版本 | 旧任务兼容、回退和远端已发生事实对账 | 不能完成跨版本恢复时阻断部署而非假回滚 |

**ADR 状态**：I-01～I-08 是设计前的硬性候选不变量；ADR01～ADR11 均处于 `PROPOSED/CONDITIONAL`，无一项被实测认定为最终生产选择。不可将「有人准备了文档」当成「架构已批准」。

## D. 两个初版可实现的物理组合（非产品结论）

**方案 M（模块化单体）：** 一个项目代码库、单个运行进程内的分层逻辑、关系型数据库事务性任务日志、隔离文件目录。优点为追踪简单，缺点是进程共故障域；须明确 Worker 的异常与内存/进程隔离策略。

**方案 H（核心+执行器）：** 权威/任务台账与受限 Worker 分离，工作单元签入、领取租约、版本复核、事件/outbox、结果对账。优点是执行隔离、能力易封装；需要事件重发、队列过期和版本兼容测试。

两案使用**相同的业务验收情境**，不能给某案凭空打“更先进”或 99.9% SLA。Temporal 与托管 Agent 平台是可比较的工作流与模型执行选择，不等同于控制平面业务权威。

## E. 先实现的结构与故障演练

P1 代码层的候选边界（可调整文件夹名，不应随意改变职责）：`goal_registry`、`task_ledger`、`decision_adapter`、`scheduler`、`authorization`、`execution_gateway`、`source_adapter`、`artifact_store`、`outcome_verifier`、`evidence_graph`、`governance`、`telemetry`。初期可合并部署，但权限执行与独立结果核验**必须保持逻辑独立**。

采用下面的一条端到端业务路径检验：[historical 03-FIRST-VERTICAL-SLICE.md](03-FIRST-VERTICAL-SLICE.md)。验收至少有：无变化真实负例、来源已变正例、来源不可用、进程崩溃/双 worker、授权撤销、模型错误结论、原始目标变更，以及预算耗尽。工作区写入最初使用临时目录；**不自动往 `main` 提交生成的结论**。

## F. 近期需要的决策输入（阻断对应步骤，不阻断草案）

| 输入 | 必须决定的阶段 | 暂行安全选择 |
|---|---|---|
| 初始部署宿主、是否全天候 | 正式持续触发前 | 本地可复现环境，不宣称生产自治 |
| 模型供应商/密钥/费用上限 | 调用付费模型前 | 抽象适配器与离线回放，不储存密钥 |
| 第一业务源与产物落点 | P1 真实运行前 | 公共 MCP 规范、隔离工作区候选 |
| 外部帐户、写动作/幂等/撤权 | P2 外部写入前 | 禁止真实远端写 |
| 用户敏感资料与生命周期 | 真实私有数据前 | P1 仅公共资料、合成任务数据 |
| 组织验证责任人/盲测任务 | 正式能力验收前 | 测试结构可先实现，未知不能填 PASS |

## G. 可核验的来源

- 历史研究：`ARCHITECTURE_DECISION_RECORDS.json`、`AUTHORITY_CONTRACT_CANDIDATES.json`、`QUALITY_SCENARIOS_AND_ARCHITECTURE_OPTIONS.json`、`DESIGN_ENTRY_READINESS.json`，现均存 ChatGPT Library。仓库只提交收敛设计，避免把未审查的历史报告复制为产品代码。
- [OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/)：工具 guardrail 的真实覆盖限度，尤其不自动覆盖 handoff 和托管工具。
- [Temporal Tasks](https://docs.temporal.io/tasks) 与 [Temporal Workflow Definition](https://docs.temporal.io/workflow-definition)：Worker、工作流事件历史及版本兼容原则。
- [GitHub Actions troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)：schedule 可能延迟/丢失，不是可靠 wake 的单一真相源。

后续接口详见 [02-AUTHORITY-AND-INTERFACES.md](02-AUTHORITY-AND-INTERFACES.md)，操作限制详见 [04-SECURITY-OPERATIONS.md](04-SECURITY-OPERATIONS.md)。

## H. 2026-10-24 实际代码基线与架构重构决策（Draft PR #36，待独立验收）

**原始目标**：用户只输入目标、约束及必要授权；总控主动识别遗漏、针对未知研究原始证据、选择合适方法、在现有可信边界下推进任务，独立从真实目标效果验收，并在重启或新对话中恢复上下文。**这不是把43个 Python 模块等同于43个服务，也不是把测试数量当成完成度。** 原始用户纠正及先前否决的“只做局部补丁、复制多套总控、让用户一再提供精准提示词、生产写入未经授权”始终优先于本文草案。

### H1. 候选目标架构与目前代码的对应

| 逻辑职责 | 当前真实接口/组件 | 已知边界、剩余问题 |
|---|---|---|
| 目标契约及跨运行恢复 | `continuity.py`、`intent_planner.py`、`intent_runtime.py` | `resume_goal` 只读恢复**已登记**的 owner 目标；尚不能自动从陌生自然语言完成全部目标解析。ChatGPT 新会话不能被假设自动读取运行宿主上的 SQLite。 |
| 任务权威、权限、租约及执行生命周期 | `ledger.py`、`runner.py`、`host.py`、`control_kernel.py` | 原有单一 SQLite 保留；架构重构对全层级任务祖先约束进行 fail-closed 审查。Host 仍是被真实操作系统唤醒的有界 tick，不是已安装全天在线的后台服务。 |
| 受限领域能力（adapter） | `capability_dispatch.py` 的静态注册表，调用现有 `knowledge_routing`、`investigation`、`research_*`、`repo_repair`、`goal_loop`、`reconciliation` 等 | 只是可信代码认可的本地/隔离能力；外部写入、任意 Skill 自动安装及自授予工具仍禁止。尚未证明开放世界方法发现。 |
| 来源检索、证据版本与候选推理 | `source.py`、`investigation.py`、`knowledge_routing.py`、`research_gap.py`、`research_assessment.py` | 来源 SHA 证明一致性而非真实性；模型检索不能自证语义正确，撤回/争议和新来源获取尚需真实效果研究。 |
| 行动与不可变产物 | `isolated_filesystem.py`、`sandbox_effect.py`、现有 repo/fixture 执行器 | 本地 sandbox 与生产远端不同；不能由工具成功自动提升为 owner 业务成功。 |
| 独立反馈和闭环治理 | `evaluation.py`、`goal_audit.py`、`conformance.py`、`outcome_feedback.py`、`local_retry.py`、`diagnostics.py` | 存在部分机械验收与重试；真实 owner 目标完成、陌生任务正确性、失败类别全范围修复及合法邻接行为还需独立证据。 |

### H2. 架构取舍

- **采用**：保留一个账本和 Host/Worker，先划定 owner goal/authority → bounded orchestration → explicit capability adapter → independent evidence/outcome 的责任线，迁移现有处理器并通过正负场景验证。
- **不采用**：将43模块重命名为微服务/新增多个自治总控/重写一套任务数据库/直接套大型 Agent 框架。除非经过对照测试发现不能满足边界要求。
- **不采用“一次性替换全部代码”**：此前的完整 blob 遍历只是源身份与结构审查，**不是每项行为都有独立语义证明**。在此信息条件下大爆炸重写会丢失未识别的合法行为。采用有端到端对照证据的递进迁移，更符合风险约束。
- **实施中的兼容层**：`runner.py` 的既有来源读/方案提议接口仍由 compare adapter 使用，以保留旧有失效注入和撤权检测。它是明确的迁移过渡边界，不是第二套控制器；正式能力集合在静态映射中可审查。

### H3. 端到端验收义务和跨会话继承

1. 目标登记及新进程恢复：先验证 `continuity.resume_goal` 的同一目标 ID、授权版本、下一任务身份和已知 `UNKNOWN`，**不**以交接文件/助手记忆伪造授权。出现两个有效目标不能臆测优先级。
2. 研究到行动：必须从用户目标发现真实信息缺口，读取适当的原始来源，明确来源可信与适用条件，提出备选方案并拒绝幻觉来源；该能力**尚未以通用未知任务证明**。
3. 任务传递：不同能力、多层后代在祖先阻止、目标修订、撤权、循环父链及租约竞争时必须拒绝执行；其他合规工作不应被无关失败挡住。
4. 执行与验证：对真实授权动作，观察实际外部效果、未知 ACK、重试幂等、合法相邻动作和失败类修复；没有可独立复核的真实业务结果不得报 READY。
5. 开发对话继承：每次先查**最新用户原始目标/明确纠正**、GitHub PR 实际 HEAD 和确切版本测试，再看根目录 `AGENTS.md` 与单一 `SESSION_HANDOFF.md`。归档交接、旧 CURRENT 与旧 ConOps 只能做历史证据；不可把 ChatGPT 记忆、GitHub 元数据、目标账本当成同一个权限系统。
6. 重构完成判据：与旧版合法路径对照、失效注入、全部当前相关回归、Graphify/AST 可追溯结构、真实陌生任务的独立结果及 owner 纠错负担；任一关键义务未验证，明确保留 OPEN 与 NOT_READY。

**状态：架构契约已梳理，运行时能力分发和完整祖先检查作为改造候选进入 Draft；并没有完成整个自主 Agent OS，也没有任何生产部署或新授权。**

## I. 2026-10-26 架构再判定：拆分“认知决策”与“可信执行”，停止用固定语法扩张冒充通用 Agent

**判定状态：对当前全系统架构的否定性评审；提出可证伪的替代组合，不是完成宣告。** 以前的 H2 中“保留原 Host 并渐进迁移”不能解释为什么原始 G1–G8 的核心能力持续没有出现。当前 Draft PR #50 核对点为 `94aea56cff10a598588cb23d2b648f45e05fba22`、对应 CI #40285610220。后续必须动态复查 HEAD/CI；本节的数字只代表这一核对点。

### 观测到的结构问题（不把诊断当作最终实测成功）

- 当前源码约 51 个 `src/` 文件、684 KB；`open_goal.py` 约 916 行，仍通过少量既有 objective / 局部自然语言模式选已注册子任务。近期要支持 `and then` 时，同时改动 parser、SQLite dependency、worker admission、parent audit、child lineage、Host progress 等多处；是**决策表示层耦合**的强信号，而不只是某条正则写错。
- `capability_dispatch.py` 明确只分派已注册工具，这是**执行安全的优势**，但若由它承担全部认知选择就天然无法在未知问题中自行比较/适配新方案。
- `host.py` 明确不把研究/候选产物晋升为语义或业务目标完成，这是对的；但没有与之相配套的通用自主规划器、竞争方案试验器、面向真实目标的独立结果验收。
- 731 项本地回归和七项 CI 作业成功能保护大量既有约束；模型实验、外部效果、真实 ChatGPT 认知执行、真实业务领域迁移并没有因此全部验收。两周持续补丁与 G1–G8 中目标驱动的陌生任务能力之间，仍存在显著偏差。
- 更早的 `PRODUCT-READINESS-GATE.md` 已于 2026-10-25 选定“目标级 planner/decision policy + on-demand 专家 + 独立 effect reviewer”；后续没有改变主要工程重心。这是**决策到执行的治理失效**，不得再写同一提案掩盖缺口。

### 各竞争方案的对照与明确处置

| 组合 | 直接解决的责任 | 障碍/反例 | 本期处置 |
| --- | --- | --- | --- |
| 原样扩张 `open_goal` 关键词、DSL、任务特例 | 窄场景可预测、可测试 | 每个陌生目标需要新增结构，修同一跨步骤契约常涉及多模块，非通用 Agent | **停止作为认知主路线**；仅修阻断安全/兼容性的缺陷 |
| 全盘重写 Host/SQLite 为 LangGraph/Temporal/托管引擎 | 持久图、事件回放、任务恢复 | 重建授权/独立效果检查，双权威、迁移和运维成本；仍未供给认知或语义验收 | **暂不整体替换**；以真实相同目标和失败注入 A/B 重新评估 |
| 在 ChatGPT/Codex 原生模型与现有工具上直接执行认知循环，以结构化协议调用受控内核 | 今天即可使用已连接的专业检索、真实 GitHub、文件及执行工具，无新增付费模型 API | 原生 ChatGPT 会话与宿主 SQLite 是不同权威面；跨会话自动调用及稳定结果须实测，不能假称 Host 已连通 | **本期主试验路径**：真实任务先证明认知→行动→独立外部读回的改善 |
| 保留单一授权账本、隔离执行、来源/证据/审计，引入模型无关的规划器接口，逐步替换固定自然语言编译器 | 旧有合法执行路径兼容；允许目标级动态比较和修正 | 需要可复用的工具能力描述、动作权限/效果契约和真实目标 oracle；不能凭一个 JSON schema 自证 | **目标实现形态**，但先用真实任务验证接口再迁移；不创建第二个总控 |
| 把 Claude Code Game Studios 的角色/Skill/Hook 直接全套复制 | 工种分离、代码检查、生产流程明确 | 49 专家角色+大量规则对单个父系统可能显著增大协调成本且仍缺可靠业务效果源 | 选择性借鉴职责分离、hook/质量门禁；不复制其数量 |
| AOCI + Graphify + 代码搜索 / Playwright / Caveman | AOCI 提供版本化“架构语义先验”；Graphify 提供结构关系；Playwright 提供页面操作；Caveman 提供可恢复压缩 | 这些都是**工具能力**而非决策总控；AOCI 描述需源证和更新治理，图不等于语义，压缩可能丢目标约束；Playwright 的UI操作不授予写权限 | 在相关任务按需组合接入，分别测试准确性/费用/合法性；不设为强制依赖 |
| UVM 式工程验收 | 将 vPlan/coverage、monitor、scoreboard、SVA 与正反故障注入理念用于 Agent 轨迹和结果 | UVM 是硬件验证方法，不负责开放式 Agent 推理；绿色测试也不能代替真实用户最终效果 | **采纳验收方法**，不复制 SystemVerilog 基础设施 |

### 2026-10-29 来源生命周期与写入路径：失效不是删除

**复现的上层故障：** 私有 Library `/Continuity/General_Learning/cognition-agent-os_ACTIVE_BUILD_STATE.json` 保留了 2026-10-23 PR #26 的 `canonical_delivery` 和 `COMPLETED_SUCCESS_EXACT_HEAD`，但文件仍在当前导航根目录并叫 `ACTIVE`；彼时状态与最新 GitHub 候选 PR #53 冲突。这是来源的**角色/版本失效**，不等于旧内容错误或必须删除。已将该原始 JSON 完整迁入 `/Continuity/General_Learning/2026-10-23/HISTORICAL_PR26_BUILD_STATE_20261023.json`，旧 PR #26 delivery review 同期归档；现行根目录只保留跨项目导航 `INDEX.md` 和属于另一知识主题的 2026-10-19 `MANIFEST.json`。这是独立的私有 Library 效果，公共仓库只引用路径/机制，不复制私有文件。

**取舍与反例：** 参考 [OpenClaw knowledge lifecycle](https://github.com/openclaw/openclaw/blob/main/extensions/knowledge/src/lifecycle.ts)（已核源码，revision/hash 前提检查、superseded/withdrawn 生命周期）及 [supersede.ts](https://github.com/openclaw/openclaw/blob/main/extensions/knowledge/src/supersede.ts)（受作用域与依赖限制），[Letta Context Doctor](https://github.com/letta-ai/letta-code/blob/main/src/skills/builtin/context-doctor/references/auditing-memory.md)（索引发现和加载效果分开验证）。不另建第二个 SQLite 或全局新控制器；先修源头的状态写入/命名规则与现有精确检索路径。**任何新的工程快照**必须带采集时间、来源角色、对应 PR/commit/CI 和有效范围；只在有可靠当前提供方读回时才可称 current，其余存于日期归档，刷新需先以当前源为准再使旧结论及依赖失效。用户原话、实时 provider 与历史工程快照属于不同权威域，不可在搜索结果中互相顶替；隐私删除与版本过期分别处理。无需因旧 PR 已合并/旧快照过期就抹掉审计轨迹。

**三个对照测试：** (a) 新旧快照同名 `ACTIVE`：以 GitHub 实际 PR/head/CI 判角色，不按搜索得分排序；(b) 长索引有一次过期标题：保留历史原文但不得把它视为当前用户目标；(c) GitHub 不可访问：返回当前工程状态 UNKNOWN，旧数据仍可作注明日期的历史证据，不可声称现在有效。上述操作已经实测私人源位置和 GitHub HEAD；但新 ChatGPT 会话是否调用本规则、衍生语义结论是否全链失效，仍未实测，整个产品 **NOT_READY**。

### 当前任务边界修正（2026-10-29，优先于旧的宿主前提）

用户明确将“持续”定义为**由用户聊天唤醒后可靠接续与执行**，而非
7×24 小时自动运行：每次新会话通过当前可用的 ChatGPT、私人 Library、
GitHub 和已安装的 Skill 恢复原始需求、历史纠正、版本/任务现状，
自主质疑研究和执行，真实读回并保留未完成工作；任务过大可在下次
用户唤醒后接着完成。对话外无可证的持续运行不得冒称发生。
Codex Goal/Work、独立 SQLite Host、定时任务和 API 桥接现在均为
**可选后续演进**，不能作为交互式父系统 READY 的前置门槛。
选择新方法前必须实测当前交互式真实效果，并与现有连接工具方案比较，
不为“持续”再造额外自治控制器或第二个目标账本。用户已经允许在真正
完成并通过独立验收后合并运行，但这不是自动认定已通过的证明；
若涉及真实部署、付费、子系统/外部生产写入，仍以具体授权范围为准。

### 优先级反转（约束后续工程行为）

1. **当前直接使用已授权 ChatGPT/Codex 工具进行真正的认知任务**。每次必须保留原始要求与关键纠正，主动搜到足够一手资料并挑战候选因果解释，在同等成功条件下比较至少两个适用解法，实际选择可行路径，检查真实工具/文件/外部结果，失败继续纠正。简单任务适应性减轻流程，不固定七项表单或 Agent 调用。
2. 对实际轨迹记录 **`Goal → Unknowns → Sources → Competing Plans → Decision & Grant → Executed Effect → Independent Outcome → Correction`**。决策、权限、实际提供方和 oracle 必须分别标注；每次相关任务的来源和最终用户条件都应可重算，不能只记“CI green”。
3. 用**同一批未经专门硬编码的真实任务**对照：(A) 现有固定 Host 模式；(B) 原生模型+真实工具+原有可信授权边界；(C) 经过有证据必要性检验的 SDK/图编排适配器。指标是完整原始目标的独立完成率、用户纠正次数、实际效果、非法/重复动作、从失败到纠正、耗时/调用成本、陌生领域迁移。不得把离线模拟模型通过记作模型能力成功。
4. 只有在 B 的能力边界和工具合同被真实验收后，才将目标级动态计划入口稳定映射到现有 Host/SQLite 的**唯一授权/效果写入权威**。不要让 ChatGPT 会话状态、GitHub 交接或模型生成计划成为新的效果授权真相。
5. 未出现真实目标端到端效果改进，不再以新造 `open_goal` 语法分支、微型状态机、更多检查器或文档数量来声称进展。旧路径必须继续通过安全/兼容回归，但新工作要么交付一个**可独立验收的真实认知→动作结果**，要么明确揭示架构方案不成立。
6. 部署、MCP 服务、付费 API、多租户、子域写迁移不属当前必须执行的动作。架构预留接口即可；真实需要时取得对应授权。普通无关 ChatGPT 会话不强制触发 cognition。

### 可推翻本期选择的证据

- 若真实同条件 A/B 表明某个成熟框架在独立成功率、授权约束、恢复与维护成本上稳定优于“原生模型 + 现有可信底座”，则迁移相应**职责层**，必要时整体换掉本地工作流内核。
- 若同一授权和来源在 Host 多处重复校验造成无法合理证明一致性，优先将共同检查折叠到唯一 Effect/Admission 边界；不能以更多并行检查器解决责任重叠。
- 若不同子域共享调用确实需要跨宿主 ABI/MCP/API，先形成受控适配器而非强迫所有子系统迁移内部状态。
- 若实测证明 Caveman/索引摘要引入目标关键约束丢失，默认退回原文和原始工具输出；压缩或索引不获得覆盖原始任务的权威。
- 需要下一次审核将对比结果填写为 PASS/FAIL/NOT_OBSERVED；本决策目前只获得源码分析与已执行局部回归证据，**尚无真实场景 A/B 通过**。

本轮参考原始官方材料：Anthropic [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)；OpenAI [Agents overview](https://developers.openai.com/api/docs/guides/agents)、[SDK](https://developers.openai.com/api/docs/guides/agents/sdk)、[Evals](https://developers.openai.com/api/docs/guides/agent-evals)；[Temporal](https://docs.temporal.io/workflows)、[LangGraph](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx)、[AOCI-CODE](https://github.com/aoci-spec/aoci-code)、[Graphify](https://github.com/Graphify-Labs/graphify)、[Playwright MCP](https://playwright.dev/docs/next/getting-started-mcp)、[Caveman](https://github.com/caveman-app/caveman)、[Claude Code Game Studios](https://github.com/zerohours/claude-code-game-studios) 和 [IEEE UVM 1800.2](https://standards.ieee.org/ieee/62530-2/11429/)。所列均为研究来源，不代表已安装、兼容、授权或验收。



## J. 2026-10-31 历史 Draft：UAOS 父级绑定迁移候选（2026-11-01 起不再是当前工作流）

**状态更正（2026-11-01）：** 本节保留的是一次历史迁移审计与候选方案，不再定义当前 owner-selected workstream，也不授权迁移四个子系统。当前目标是先证明 **cognition-agent-os 自身的认知/演化闭环**：完整目标恢复、竞争根因诊断、第一手研究、方案反证、授权执行、独立 owner outcome、程序性学习与跨任务迁移。UAOS 子域迁移仍是独立目标，只有 owner 重新明确选择时才启动。此更正优先于本节中“当前优先候选”的历史表述，并与 `AGENTS.md`、`docs/PRODUCT-READINESS-GATE.md` 一致。

**新用户目标（不是对方案正确性的证明）：** 在 cognition-agent-os 内，每次工程决策都必须执行恢复原目标与失败经验、定位问题与竞争根因、阅读适用的一手源码/测试、比较 reuse/adapt/replace/delete/build、提出可推翻选型的反例、合法执行、真实结果独立读回、沉淀有效方法与失效条件。简单已知事项可以缩小研究成本，但不能跳过目标、反证和验收。不得仅靠这段规则声称 ChatGPT 新会话已自动执行。

**观察（源代码与正式业务状态）：** 2026-10-31 四个子域的 manifest+adapter+capability 仍指向旧 UAOS，原审计仅扫描 `manifest.binding`，遗漏 `manifest.parent_control_plane` 顶层规范性引用（A 股子系统实际存在该字段）。本 Draft 修改 `domain_contract.py` 复用同一个只读合同审计入口，增加顶层扫描，并补反例：将 controller 字段改为新认知父级，但保留顶层旧 parent 字段时必须报告旧依赖且不能授予迁移权限。保留未知域与合法原路径，不写子系统数据。

**更强的反例（子域实际测试）：** `video-growth-agent/tests/test_uaos_current.py`、`financial-writing-agent/tests/test_uaos_cognition_evolution_inheritance.py`、`novel-writing-agent/tests/test_authority_behavior_contract.py`、`a-share-event-driven-agent/tests/test_common_behavior_binding.py` 都包含硬性旧父级假设。因此迁移时不仅需改变 JSON 引用，还必须以原业务验收替代这些旧架构字符串断言；否则新接口正确也会被旧测试拒绝。不能把调整测试为绿色当作业务验证。

**竞争方案与再质疑：**

| 候选 | 价值 | 反例及成本 | 处置 |
|---|---|---|---|
| 全盘复刻 UAOS 再一次性切换 | 旧接口表面兼容 | 继承旧错误、难以明确业务收益；隐藏绑定会造成假迁移 | 否决默认采用 |
| 旧 UAOS 与新系统长期双控制器共存 | 短期兼容 | 两个权威、额外维护、相互矛盾 | 否决作为长期终态 |
| 一次性重写四个子域并删除 UAOS | 清理速度表面最快 | 业务 ID、长期素材/正典、授权与回归难独立证实 | 暂不授权 |
| 逐能力迁移／必要时重构整个子域，真实验收后删除对应旧接口 | 可测试可回滚、能优先移除确认无用的能力 | 临时过渡层可能变成永久负担；需设置退出验收 | **当前优先候选，继续挑战** |

**一手方法证据：** [Martin Fowler《Strangler Fig》](https://martinfowler.com/bliki/StranglerFigApplication.html) 强调目标导向、按可替换业务边界逐步交付，而不是逐字照搬旧实现；[AWS Strangler Fig](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html) 说明转换、共存、删除旧功能与回滚风险；具体 Agent/记忆/工作流方案先沿已有 Agent-Learning-Hub 方法卡进入源码与反例，不引入额外控制器。

**最强反证：** 如果某子域新架构无法实现合法旧任务、不能独立观测效果、对最新资料的记忆继承失败或有旧 UAOS 隐含权限依赖，则不应以“新代码更少”宣告迁移成功。反之若某旧功能完全无调用者或被独立替代且可回退，应优先删除它，而非以“历史兼容”无限延期。

**实施与验收边界（历史决策）：** Draft 曾修复一处实际旧引用漏检，不意味着整域接管。后续若 owner 重新选择该迁移目标，仍须对一个业务场景进行旧路径与新候选的真实同任务对照，测量全目标完成、用户纠错次数、成本、原业务状态/权限、失败恢复与负迁移。

**工程合并权限更正（2026-11-01）：** owner 已将工程合并就绪判断委托给 assistant；assistant 可在独立检查完整 owner goal、相关独立 review、exact-head CI、未解决 P0/P1/P2、rollback 与 acceptance evidence 后自行决定合并 main，无需逐次申请合并批准。这是判断权限，不是必须合并，也不放宽产品验收。部署、付费 API、子系统生产正典写入、私有 transcript 发布及插件账号发布仍需各自明确授权。


## K. 2026-11-01 当前工作顺序：先证明认知/演化闭环，不以局部工程量替代

**当前 owner-selected objective：** 完成 cognition-agent-os 自身的 cognition/evolution loop，而不是 UAOS child migration、静态文档审计、额外 graph/controller 或 CI 数量。完整闭环是：恢复原始目标与纠正 → 定位竞争根因 → 研究一手来源 → 比较并反证方法/工具 → 在当前 grant 内执行 → 独立读回 owner-meaningful outcome → 形成带适用条件/失败条件/反例的 procedure → 在不同任务中重新验证、迁移或失效回滚。

**已修复的窄范围 P2（Draft PR #62，NOT product acceptance）：**
- auditor 与 sandbox effect 统一使用 128 KiB artifact bound；66,387-byte 有效 goal-case artifact 回归验证 exact audited bytes 被 stage。
- goal-case audit failure 绑定 exact observed artifact digest 到 research-reentry CAS；不同 corrupt byte revisions 不得复用旧 CAS；audit verdict 使用真实 status 分类。
- source/evidence failure 时只允许当前注册 root、当前 SQLite goal/grant/write authority 下的 scoped read-only investigation；披露后重查 grant、original goal 与 exact source digest；决策/动作 admission 仍关闭。

**下一项真正的产品缺口不是再加固定 grammar：** 当前 `intent_planner.py` 仍只注册有限 objective；`public_tool_discovery.py` 能发现 metadata，但不等于把新工具安装为可执行 Worker capability；`owner_postcondition.py` 只独立验证少数明确的本地结果。必须用一个真实、此前未为系统硬编码的 owner goal，观察 native model/tool 选择、实际合法执行和独立 owner outcome，再与 incumbent 在同等授权/输入/时间预算下 A/B。若没有真实 client/Host trace，标记 NOT_TESTED。

**程序性学习边界（2026-11-02 更新）：** `knowledge_candidates` 仍是 root-scoped、source-pinned、unverified candidate；`signed_outcome_feedback` 仍是受签名/holdout 约束的窄领域反馈，不是通用跨任务 method library。现有 `procedure_evidence.py` 是同一 SQLite ledger 的只读投影，单次最多跨 keyset 页面扫描 512 个当前 grant 下的其他 native roots（每页 64；预算耗尽且有更多候选时返回 `PROCEDURE_TRIAL_SEARCH_INCOMPLETE`）。正向 `items` 只收录“原始完整 owner-local postcondition 现在仍可独立复验、且对应最后一个已登记 intent”的不同 goal 成功试验；负向 `failure_items` 只收录两个已明确分类的 Worker 拒绝（`JOIN_KEY_AMBIGUOUS`、`NO_SAFE_GOAL_PLAN`），并绑定失败事件、任务、带 role 的来源 SHA、有限长度且明确标为不可信的历史决策理由/挑战/证伪条件，以及 prior-root observation digest；不复制历史目标原文。基础设施异常、权限阻断、验证器不可用不被伪装成方法失败。正负证据一起进入同一个 digest，并在 admission 时重新计算；源、artifact、grant、lineage 或失败结果变化都会使对应证据退出或令旧 digest 被拒绝。模型必须比较失败的来源条件与当前任务，不自动封杀方法，也不把失败解释成根因。它不写新表、不提升 memory、不创建可执行 capability、不授权行动，也不证明 general method transfer 或 cross-domain transfer。当前仅提供可复验的本地能力家族成功案例与有限失败反例，仍不等于可迁移 procedure 已学会。

**当前状态：NOT_READY。** Draft PR、绿色测试、模型文字或方法卡均不能代替 first-turn fresh ChatGPT session activation、陌生 owner task 的独立结果与纠错负担测量。PR #62 是本轮指定集成候选，而非仓库唯一开放 PR；产品/交互验收仍 OPEN。


## K. 2026-11-01 架构根因重开：允许替换认知层，禁止再以补丁数量衡量进展

**触发的用户纠正：** 多轮修复仍未获得原目标的独立验收。用户明确允许重新学习原始 Agent-Learning-Hub / Hello Agents，并把上层架构错误、删减、重构甚至推倒重建作为正式备选。此处不是对当前架构的批准；本轮重新开放 I、J 的既有选择。

**实际观察，而非结论：**
- 当前 main 的 `host.py::run_tick` 同一函数管理 due tasks、native plan、Worker 反馈重规划、local review/recovery、conformance、goal drift 等多个工作路径；`native_decision.py` 约 1,577 行，`native_local_planner.py` 约 1,164 行。长度本身不证明错误，但职责交织、改动波及率可以验证。
- 现有 native 方法是固定 registered objectives 的合法受控执行入口；它保留权限安全，却不能凭此证明未见领域的自主工具选择和深层因果研究。
- PR #62 的第一个“previous_result_task_id → 因果父边”实现被既有反例推翻；随后版本化 review 迁移在第一次 exact-head CI 中触发大量旧入口拒绝。修正后 exact-head CI 41302410522 全部必需作业 PASS；这验证回归与打包，不验证真实认知收益。
- 当前历史 ADR 已经建议实际任务 A/B，但工作仍偏向代码与离线断言；**“有实验计划”不能当成“实验已完成”**。

**向根因追问，保留竞争解释：**
1. H-ARCH：认知层与确定性 Host 的职责没有真正解耦，所以每次改“决策/研究”都扩散到 receipt、planner、Host 和 test fixtures。反证：在相同陌生任务上已有代码无需改动即可比候选架构表现更好。
2. H-EVAL：缺少足以区分“通过已知程序测试”和“完成原用户目标”的真实在线对照与独立语义 oracle；这可以解释绿色回归却持续 NOT_READY。反证：已有可重复、包含陌生任务和独立成果验收的真实比较记录。
3. H-MODEL：当前工具或本地模型认知能力/上下文/信息源不足，而不是控制架构问题。反证：相同模型与同样工具、预算在另一种编排下持续完成同类未知目标。
4. H-CONTEXT：长时间对话及旧材料上下文混入，导致已经证伪的选择反复引入。反证：干净会话、严格版本源与反例检索下仍复现相同失败。
5. H-MIXED：上述因素组合，不能预设只有一个单点根因。

**真正竞争的架构候选（不锁定原选择）：**

| 候选 | 保留和删除 | 是否应晋级 |
| --- | --- | --- |
| A：继续现有 Host 上打补丁 | 保留一切，包括原多入口与当前 native planner；仅对单个问题局部修 | 作为基线，不再默认胜出 |
| B：重新分层的轻量认知核心 | 保留现有单一 SQLite 权限账本、Worker、effect/oracle；把模型驱动的调研、候选方案、反证、工具选择、回退编排作为**可替换的无效果权限层**，移除重复上层分支（只在替代路径通过后删除） | 首选实验假设，不是最终产品决策 |
| C：采用成熟 Agent SDK / graph harness 做认知编排 | 替换重复的高层 loop/recovery，复用其状态/interrupt 语义；仍必须经原权限与真实结果合同接回 | 与 B 同任务对照，若显著胜出可替换 |
| D：重写整个 Host / SQLite | 连授权账本、调度和效果检查一起重建 | **条件性选择**：只有 A/B/C 无法在职责或复杂度上消除已证实阻碍，且 D 的迁移/回滚试验超过现状时启动；不以“清爽”为依据 |

**本轮重新选择的理由：** Agent-Learning-Hub (README, checked 2026-11-01) 要求先证明为什么 agent 优于固定 workflow，随后建设有限循环、严格 tool schema、trace、eval 和 safety；Hello Agents 区分固定流程与 AI-native Agent；Anthropic `Building effective agents` 也强调由简单可组合系统起步，复杂度必须以效果证明。三者是方法先验，不是本项目验收。结合上面的实际源码，B/C 与 A 的对照比直接 D 更能隔离“认知层问题”与“安全内核问题”，但如果 B/C 负面证据充分，**必须允许重新评价 D，不保护现状**。

**可执行的同任务 A/B/C，不接受源码绿灯代替：**
- 固定 3 组真实、此前没有专门加入 objective/正则/测试答案的任务：陌生软件故障的竞争根因诊断与可验证修复；跨来源研究后有证据的方案取舍；曾成功方法在**不同目标**下的迁移与失败撤销。为每组提供明确 owner postconditions 和独立检查数据。随机化顺序或隔离上下文，防泄漏。
- 三个候选共享**相同原始目标、初始来源、工具权限、模型、时间/调用预算**。A 的固定代码路径可以明确返回 unsupported；B/C 不得依靠偷偷添加 task-specific hardcode 获胜。
- 记录 source versions、所有行动与 grant、决策反证、真实工具调用、结果读取、完整 owner outcome、超时/费用、人工纠正、未知任务成功率、回归影响面。至少一次做中断恢复、过期来源、错误模型建议、工具拒绝和未授权写的负例。
- 以完整目标**独立成功率与授权零越界**为硬门，之后按纠正次数、恢复质量、维护影响面与执行成本比较。局部测试数与代码长度不作单独胜负。
- B/C 在相同案例没有可测收益则撤销新增编排，继续反问 H-EVAL/H-MODEL/H-CONTEXT；若 B/C 明确改进则逐能力切换，验证合法旧路径后删除对应重复控制层；若所有候选失败则重新开放底层协议和全重写 D。
- 在完成上述独立 A/B 前，**冻结新增固定自然语言 grammar / 多余控制器 / 粉饰性的 review 字段**。允许修安全漏洞、跨平台阻断和已实证错误；不允许这些修复自行被记作产品认知进展。

**当前结果：** 架构根因重新登记，H-ARCH/H-EVAL/H-MODEL/H-CONTEXT 尚未通过实验判别。B/C 为待做实验，D 是被明确允许的有条件替换方案。尚无真实 A/B 结果、跨任务方法晋升证明、跨会话可靠触发证据；`NOT_READY`。PR #62 继续 Draft，不因 exact-head CI 绿色直接合并或部署。

研究来源：
- https://github.com/datawhalechina/Agent-Learning-Hub
- https://github.com/datawhalechina/hello-agents
- https://www.anthropic.com/engineering/building-effective-agents
