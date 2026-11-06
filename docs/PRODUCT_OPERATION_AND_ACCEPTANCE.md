# CAOS managed interactive runtime

Status: **NOT_READY for the complete cognition product**. The managed local
runtime below is executable and tested. It is not an installed ChatGPT app,
an account-wide hook, a universal natural-language judge or an autonomous
cross-domain learner. New CLI/MCP goals are atomically managed. MCP admission,
Worker tick and local-model execution reject unmanaged historical roots; their
read/research paths remain available. The trusted low-level Python API retains
legacy compatibility, including its arbitrary-goal semantic admission limitation.

## Install and start locally

Requires Python 3.11+ for MCP. Run from the reviewed repository checkout:

```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe -m pip install -e ".[mcp]"
.venv/bin/python -m pip install -e '.[mcp]'
.venv/bin/caos --state /absolute/private/caos-state init
.venv/bin/caos --state /absolute/private/caos-state goal --file /absolute/private/goal.txt --request-id original-goal-001
.venv/bin/caos --state /absolute/private/caos-state doctor
```

Keep the complete original goal in `goal.txt`; reuse the request ID for retries.
Put authorized local evidence in `caos-state/sources`. Keep the entire state
directory private and outside Git. No API key or additional paid model is used.
The calling ChatGPT/Codex model performs investigation and method selection.

`doctor` prints the exact stdio command. A supported local Codex client can
register it with:

```bash
codex mcp add caos -- /absolute/repository/.venv/bin/python -m cognition_agent_os.session_cli --state /absolute/private/caos-state serve
```

On Windows use the absolute `.venv\Scripts\python.exe` path. Adding this
connection is an operator/account action; this repository does not install it.
For Work with shell access, the same `caos` CLI provides direct access without
claiming a native MCP connection. ChatGPT web requires an authorized remote
plugin/connection; local `config.toml` does not connect the web account.
See the [official MCP connection guide](https://learn.chatgpt.com/docs/extend/mcp).

After restarting Work, run `caos --state /absolute/private/caos-state list` to
recover root IDs instead of relying on chat memory. Follow `next_after_task_id`
with `list --after-task-id ID`. Read a selected root with `inspect --root ID`;
follow `next_after_event_id` using `inspect --root ID --after-event-id NUMBER`.
The command never chooses a goal merely because it is newest.

The existing Codex recovery hook can also read this same state when its
`COGNITION_AGENT_OS_DB`, `COGNITION_AGENT_OS_WORKSPACE` and
`COGNITION_AGENT_OS_FIXTURES` environment settings point to `ledger.sqlite`,
`workspace` and `sources` respectively. It now includes cognitive revision,
amendment/input/node counts and versioned readback locators. Startup output
does not embed correction/message/source text. Explicit state readback includes
corrections; `--readback-cognition ROOT REVISION nodes|inputs CURSOR` pages
original messages or derived nodes. Follow `next_after_event_id`; changed
state/source bytes reject stale locators. Conflicting roots remain separate.

This is tested script wiring, not proof that a client loaded the hook. Local
hooks require supported execution and trust. Cloud-orchestrated ChatGPT Work
does not support local/plugin command hooks, even when some tools run locally;
ChatGPT web does not read local Codex config. In this Work environment the
explicit CLI route remains available. See the official
[MCP support boundaries](https://learn.chatgpt.com/docs/extend/mcp) and
[plugin support](https://learn.chatgpt.com/docs/plugins).

## Use in a connected session

### Plain-language terminal entry

After explicit `init` and installation/sign-in of a compatible Codex client:

```bash
caos --state /absolute/private/caos-state chat
```

Type your task directly. With no existing goal, the first message creates it;
with one existing goal, that goal is resumed. Several goals are shown for
selection. `--new` starts a distinct task; `--root ID` selects an existing one.
Use `/exit` to close. For a multiline UTF-8 message without authoring JSON:

```bash
caos --state /absolute/private/caos-state chat --message-file message.txt --request-id message-001
```

When several goals exist, file mode requires `--root ID` or `--new`.
`--client /path/to/codex` selects the installed client and `--timeout SECONDS`
bounds a model turn (default 600). This entry requires app-server support and
uses the existing native provider/account settings; it does not log in, extract
credentials or change the provider. The local native shell is read-only and
permission escalation requests are declined. Existing CAOS MCP effect contracts
still govern CAOS actions. Other operator-configured connectors retain their
own authority boundaries.

Messages are saved before inference, including answers to clarifying questions.
Temporary native threads recover prior work through the same MCP ledger; there
is no parallel conversation database. Assistant replies are untrusted history,
not approved goals, rules or verified outcomes. The delivery history is available
through `history --root ID` and `cognition_client_history`. Metadata is returned
by default; `--include-text` (MCP `include_text=true`) reads exact replies and
questions. Follow `next_after_event_id` to page older records.

Each completed assistant item is saved immediately, before the enclosing turn
ends. A later disconnect therefore preserves that completed content. Streaming
deltas that have not reached item completion are display-only and may be lost.
Turn receipts reference saved item event IDs; older turn-level histories remain
readable through the same interface.

If a connection dies after dispatch, the delivery is UNKNOWN and the same
request ID cannot automatically execute again. Read the input/history and actual
effect state before deciding what to do next. A new request ID must not be used
as a blind retry. An already-running effect may have completed; terminating the
client is not rollback. Failed/interrupted turns do not return a successful turn
status. Even a completed turn is separate from the independent contract outcome.

**Validation boundary:** real subprocess protocol peers and cold MCP readback
are tested. Official Codex 0.167.0 also passed real CAOS discovery/goal readback
and required-server failure rejection on Linux and Windows (commit `5f1ccc8`,
run `42197902683`). Actual successful native inference through this entry remains
unverified in Work: the installed client's read-only runtime directory prevents
startup. This is an engineering entry under validation, not a download-ready
product release or a claim that all ChatGPT messages are intercepted. Ordinary
ChatGPT and the native `launch` UI still have their own message paths.

### Bounded native goal loop

For a task you explicitly want continued across model turns:

```bash
caos --state /absolute/private/caos-state chat --goal-budget 40000 --timeout 1800
```

Select the existing goal and type the continuation request, or use `--new` for
a distinct goal. This opts in to the installed Codex client's native goal loop
for this invocation, with its token accounting and a wall-clock timeout. Existing
provider/account usage terms apply; the command does not purchase or configure
a model. Ordinary chat does not activate the native goal engine.

The complete goal stays in CAOS. Its native continuation points to that root,
then reads original wording, amendments and inputs through MCP. Native goals
require persistent native threads: this mode retains conversation state in
the client's normal local storage and records the thread ID in CAOS delivery
events. It creates the native goal paused, saves input, then activates once.
A completed model turn does not end the loop; native block, pause, usage/budget
limit or completion does. `CLIENT_GOAL_COMPLETE` means the native engine stopped
as complete; the separately reported contract outcome may still be false.

On timeout/disconnect, input and unknown delivery remain recoverable. The adapter
requests a native pause when possible, then closes; this is not rollback or
proof all effects stopped. It does not automatically restart, replay an unknown
delivery or replenish budget. A later explicit fresh invocation
has its own budget: inspect delivery/effect history first. The runtime uses the
same MCP contracts and shell restrictions as ordinary chat. Real model-driven
continuation and full owner-outcome quality remain open acceptance work.

To continue a cleanly stopped native session with its history and usage:

```bash
caos --state /absolute/private/caos-state chat --resume-client --goal-budget 80000
```

The budget on resume is the **total**, including tokens already used. Omitting
the thread ID works only when the selected CAOS root has exactly one recorded
native goal thread. If several exist, use `--resume-client THREAD_ID` from that
root's delivery history; the newest is never chosen automatically. The adapter
verifies the recorded root binding, actual native thread ID/workspace, objective,
stopped status and usage before resuming the same thread. It omits the objective
when updating the budget, preserving the original native creation time and usage.
No automatic new-thread fallback occurs on mismatch or unavailable native state.

Unknown/in-flight deliveries are not resume candidates: inspect real effects
before another deliberate invocation. Snapshots moved to a different workspace
cannot silently resume a native thread bound to the old path. The complete CAOS
goal and sources remain independently recoverable even if native history is
unavailable. Model-level recovery quality is not established by a paused-thread
control test.

### Session-scoped local Codex launch

After installing this package with its MCP extra and installing/signing in to
the supported local Codex client, start an interactive session with:

```bash
caos --state /absolute/private/caos-state launch --check
caos --state /absolute/private/caos-state launch
```

Use `--root ROOT_ID` to select an existing goal, or leave it out to discover
goals without assuming the newest is correct. `--client /path/to/codex` selects
an already installed executable. The launcher passes the same interpreter,
state path and required MCP server through per-session configuration. It does
not write account settings, capture credentials, log in, change the model or
relax the client's sandbox. Existing client provider/billing settings apply.
Missing state, root, client or MCP dependency fails before starting the client.

`--check` now starts the configured MCP child, verifies required tools, and
performs a read-only state call with a 20-second timeout. Its diagnostic receipt
does not include the goal text. The child is bound to this CAOS installation
and excludes Python environment overrides and working-directory path insertion,
while retaining normal installed dependencies, including user-site installs.
Inherited PYTHONPATH cannot silently substitute another package. This proves the local
MCP transport, not model authentication or goal achievement. A successful
native-client exit also does not establish those outcomes. The current Work
environment's isolated client probe still times out with a plugin-authentication
401; this launcher does not repair account credentials. MCP guards apply to
MCP actions, not every tool available in the native client.

Ask the connected client to work on the registered goal. It can discover it with
`native_goal_list` (follow every cursor), then `cognition_session_inspect`.
The response contains the original wording, corrections, source freshness,
dependency failures and a revision token. Follow `next_after_event_id` until
null when recovering a full graph; pages share a token only while state and
sources are unchanged. Never treat the newest goal as an automatic selection.

The model can record sourced observations, competing hypotheses/options,
decisions and methods with `cognition_node_record`. These records are proposals;
their presence does not establish deep research or semantic correctness.
An obligation must quote actual goal/correction text. Source claims must quote
actual bytes with the matching SHA. `cognition_reopen` invalidates the named
ancestor and its descendants; unrelated branches remain current. Corrections
use `cognition_goal_amend`; they preserve the original and invalidate previous
derived decisions/contracts. A revision conflict requires a new read, not an
unconditional retry. An identical request ID safely replays a lost response.

New conversation messages and external research first use
`cognition_input_record` (`text`, `origin`: `client_user` or `external`, `locator`,
`request_id`, `expected_revision`). This preserves wording without amending the
goal. Origin/locator are caller assertions, never authenticated owner identity.
Read full messages with `cognition_inputs_inspect`; follow its cursor. `inspect`
reports input/uninterpreted counts without repeating full raw messages.

Record a tentative reading with the existing `cognition_node_record`, kind
`interpretation`, plus `input_refs` (`request_id`, `sha256` from input readback)
and `claims` (`input_id`, exact `quote`, `category`, `meaning`, `basis`). Categories
are goal, constraint, preference, correction, implementation_suggestion,
action_request, reference, assumption. Basis is explicit, inferred or uncertain;
none means verified. One mixed message can have multiple claims. Link downstream
hypotheses/options via `depends_on`; supersede a wrong reading to invalidate its
dependent work. Two unsuperseded readings stay visible. No category automatically
edits a goal, grants tools, or promotes a method. A genuine correction still uses
the explicit amendment/reopen paths above. Correct interpretation and client
routing remain open.
For managed actions, later input now blocks the old decision at the shared
admission/effect check. Recording an interpretation alone does not reactivate
it; a new decision and valid action binding are required. This ordering check
cannot determine whether a model understood or obeyed a user's correction,
and it cannot control unrelated client tools or effects already in flight.

Work CLI equivalents: `receive --root ID --file message.json` accepts the same
body, and `inputs --root ID` pages original text. `record` saves the interpretation.
The client prepares these records; the user need not author JSON. MCP graph and
input readers require `allow_source_read`, because derived copies may contain
source quotes. `serve` enables it for the selected private local state; a custom
read-only MCP profile must opt in explicitly.

A decision that proposes execution includes `action_spec`, exactly the typed
child capability spec it selected. Admission rejects a different action even
when that other action is operator-authorized. Decisions without `action_spec`
remain available for investigation but cannot authorize execution. This binds
the decision to the Worker action; it does not certify its semantic reasoning.

## Approve effects and independently check results

Managed sessions cannot execute a model's proposal merely because it passes a
JSON schema. An operator first reviews and binds an executable contract:

```json
{
  "version": 1,
  "goal_sha256": "copy the current goal_sha256 from inspect",
  "effects": [],
  "outcomes": []
}
```

Each allowed effect has `spec` (the exact registered child capability spec)
and `prerequisites` (checks that must currently pass). Each outcome is a check
with `space` (`sources` or `workspace`), relative `path`, `test` (`sha256`,
`text_contains`, or `json_equals`) and expected `value`. Example:

```json
{"space":"sources","path":"approval.txt","test":"text_contains","value":"approved"}
```

```bash
caos --state /absolute/private/caos-state authorize --root ROOT_ID --file reviewed-contract.json
```

This command is **not a model-visible MCP tool**. A model may draft a contract;
that draft is not an authorization. Empty effects authorize no effect; empty
outcomes never pass. Binding a contract cannot automatically prove it captures
every natural-language clause. A trusted operator/evaluator must establish that
mapping. This remains a product limitation, not a solved cognition claim.

`native_decision_admit` uses the existing ledger/Worker after checking the
contract, actual prerequisites and current decision dependencies. The Worker
checks them again, including at the existing artifact-write guard. A correction,
withdrawn prerequisite or reopened ancestor blocks a pending effect.
`native_local_tick` executes only the chosen goal's pending child. Managed
ledgers reject standalone typed/CLI enqueue bypasses. The old low-level ledger
API also rejects revoked grants and nonexistent/stale parents before enqueue.

`cognition_contract_outcome` rereads actual bytes against operator checks.
`CONTRACT_VERIFIED` means those checks passed, not universal owner success.
Existing `native_owner_outcome` independently validates its supported narrow
local contracts. Provider business results need their own genuine validators.

The security boundary is the scoped MCP surface and trusted operator runtime.
An agent with arbitrary shell, SQL or another connector's write permission can
bypass this boundary. CAOS does not intercept those tools or authenticate
client-supplied corrections as the account owner.

## Learning, interruption and recovery

`cognition_method_trial` attaches a different goal's independently reread
contract result to a versioned method. `cognition_method_trials` rechecks source,
method and result versions; changed/failed evidence returns
`REQUIRES_REINVESTIGATION`. These are scoped trial associations. They do not
prove the method caused success, generalize across domains, or automatically
rewrite a Skill. Semantic evaluation and controlled promotion remain OPEN.

An executing decision can cite `method_refs`, each with `root_task_id`,
`node_id` and `use` (`experiment` or `reuse`). The same admission/write guard
revalidates these references with the existing method-trial reader. A missing,
withdrawn, changed, failed or incompletely scanned trial dependency blocks the
effect. `reuse` requires at least one current passing scoped trial; `experiment`
allows an untried method without declaring it proven. Changed observations
invalidate queued bindings even if the new observation also passes: the model
must inspect the new evidence before a fresh decision/operator rebind.
This checks declared dependencies, not undisclosed copying of a method or its
semantic applicability to a new domain. Passing associations do not prove cause.

For a private cross-session snapshot:

```bash
caos --state /absolute/private/caos-state snapshot --file /absolute/private/caos-session.zip
caos --state /absolute/private/restored-state restore --file /absolute/private/caos-session.zip
caos --state /absolute/private/restored-state inspect --root ROOT_ID
```

Snapshots use SQLite's backup API (including committed WAL data), hash every
file and include source/workspace bytes. Restore rejects path traversal,
duplicate paths, corruption and oversized archives. It refuses existing
destinations, preserves original IDs/history, and fences effects. A snapshot
may contain private goals and evidence: never attach it to a public PR.

After checking current authorization and source freshness, the operator may
bind a reviewed contract with `authorize ... --rebind-pending`. This revalidates
and rebinds only PENDING children in that root, preserving the old binding in
history. It does not replay RUNNING/unknown external effects. Those require
independent reconciliation. Never restore an old snapshot over live state.

For rollback, retain the prior checkout and a private snapshot. Do not run an
older runtime against a managed ledger: it does not enforce the new policy.
Inspect snapshots read-only until the chosen version and permissions are
reviewed. No main merge, production deployment, account change or private
plugin release is implied by these commands.

## Reproduce engineering evidence

With pip/setuptools and the MCP extra already installed, a single offline run
builds a wheel, installs it into a fresh disposable environment, tests the actual
CLI, runs regression/static checks and both real MCP transports:

```bash
python scripts/verify_delivery.py --output /absolute/private/new-acceptance-run
```

Use `--build-python /path/to/python` if setuptools lives in a different existing
interpreter, or `--mcp-python /path/to/python` for the installed MCP environment.
No dependency or model download is attempted. Output must be a new
directory outside the checkout. `receipt.json` binds each exit status and raw
log hash to the actual source fingerprint before/after execution (including
uncommitted files); source changes during a run fail the aggregate verdict.
`--profile core` or `--profile transport` scopes a run explicitly. A scoped PASS
never means all checks or the complete product passed. CI uses the same
transport command on Linux and Windows. Review raw failure logs on demand;
reuse `plan_incremental_audit.py` for exact-blob source inventory, not semantic
acceptance. These commands do not merge, install on the owner device or connect
an account.

Individual probes remain directly usable:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/verify_assurance_registry.py
python scripts/verify_effect_boundaries.py
python scripts/verify_native_mcp_transport.py
python scripts/verify_managed_cognition_transport.py
```

The managed transport probe uses the actual official SDK and separate server
processes: missing-contract rejection, legal local effect, independent SQL
outcome, cold recovery and ancestor-reopen blocking. It uses explicit operator
policies and synthetic fixtures. It is **not** the original M033 natural-language
accuracy benchmark, a real new ChatGPT conversation, a model A/B experiment,
or completion of the full owner requirement set.

Still OPEN: automatic faithful contract derivation; independently evaluated
recursive research on unseen tasks; stable fresh-chat positive/negative entry;
cross-domain method improvement and non-fit detection; production provider
outcomes and a durable user-authorized account connection. These obligations
must remain open even when all engineering checks are green.
