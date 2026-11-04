# CAOS managed interactive runtime

Status: **NOT_READY for the complete cognition product**. The managed local
runtime below is executable and tested. It is not an installed ChatGPT app,
an account-wide hook, a universal natural-language judge or an autonomous
cross-domain learner. Existing unmanaged entrypoints retain their compatibility
contract, including the known arbitrary-goal semantic admission limitation.

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

## Use in a connected session

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
