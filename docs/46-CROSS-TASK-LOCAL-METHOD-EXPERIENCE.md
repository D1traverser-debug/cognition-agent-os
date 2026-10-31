# Cross-task local method experience (P35 slice)

## Purpose

A later native-goal decision can now see method patterns that worked for other
owner goals. This closes one narrow gap between per-task feedback and
cross-task transfer. It is not general autonomous learning, a domain expert,
or a business-outcome oracle.

## Authority and evidence model

The new read-only projection over the existing SQLite task ledger creates no
task, table, scheduler, grant, external request, model call, or production
effect.

A historical example is eligible only when:

1. The original root is a currently registered native goal under the same
   current goal/grant revision as the task being planned.
2. The native decision audit replays the registered decision, source pins,
   child identity, immutable artifact and independent mechanical audit.
3. The original-owner local postcondition oracle freshly rechecks the complete
   supported owner-local result.
4. The final owner evidence task is exactly the final admitted decision child,
   and the mechanical verdict matches the typed objective.
5. The result scope is one of two independently supported local scopes:
   ORIGINAL_NAMED_READONLY_COMPARISON_REPORT or
   ORIGINAL_SANDBOX_DRAFT_POSTCONDITION.

A method family is surfaced only after two distinct owner-goal text digests,
two distinct source-binding digests, and two distinct result-artifact digests
independently pass. Repeating the same goal and source binding under another
task ID does not count as replication. The scan is bounded to 64 recent
registered native roots with an admitted decision; truncation is reported.

## Integration

The native local planner includes the projection as
replicated_cross_task_method_experience. The model must treat it as an
advisory prior, challenge applicability and failure modes, bind only the
current task's source paths, and never let it override the exact owner
contract. No method card is an executable capability.

The method families are intentionally typed and narrow:

- compare_records: preserve the owner's reference-to-observed role order,
  compare original records read-only, and independently recheck the report.
- ensure_structure: construct an isolated draft, preserve original content,
  add only requested fields, and independently read back the sandbox result.

The projection is recomputed from current bytes on every planner call. Source
drift, grant revocation, missing artifacts, ambiguous owner language, or
failed audits remove the affected example from the current result. There is no
mutable promotion flag to trust.

## Explicit non-claims

- This does not establish semantic truth for arbitrary goals.
- Local owner postcondition success is not external business success.
- It does not generalize from unverified research prose or mechanical PASS.
- It does not authorize unregistered tools, external APIs, production writes,
  code deployment, or permission changes.
- It does not yet discover novel procedures from arbitrary source code.
- It does not prove behavior across different goal/grant revisions.
- The existing SQLite ledger is not cryptographically immutable against an
  actor who can rewrite the database and all local files.

## Regression coverage

tests/test_native_method_memory.py checks one-example abstention, two-goal
replication, duplicate-goal/source rejection, live source-drift invalidation,
and injection into the next native model decision. Model transport is mocked;
the ledger, Worker, artifacts and owner-result verifier are real.
