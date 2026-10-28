# P16 — Durable negative hypotheses and bounded alternative synthesis

## Cause demonstrated by actual model experiments

P14's real local Ollama model evaluation found 0/2 repaired tasks
for Qwen2.5-Coder 0.5B, 1.5B and 3B. P15 added the actual wrong
PUBLIC JSON result to the model's public feedback (instead of only
the wrong-result SHA). The genuine P15 three-billion-parameter
evaluation, [Actions 39557639097](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39557639097),
found **2/2 structurally frozen first proposals, 0/2 public pass
and 0/2 hidden pass**. Both subsequent generations were duplicates
of a provably failed candidate, and the earlier P13 loop immediately
returned `MODEL_REPEATED_PRIOR_HYPOTHESIS`. The improved observation
alone did not cause the small model to revise its hypothesis.

A duplicate is not new evidence of success. It is negative evidence
that the model or sampling method has not escaped the wrong candidate.

## Real change to how the existing worker behaves

The original `repo_refinement` loop (not a parallel controller)
now reuses fingerprints of earlier model-generation attempts recorded
in the original SQLite event ledger, including across manual calls.
On a duplicate, unchanged original source or malformed candidate:
- the actual generated candidate's SHA fingerprint is retained
  without storing unbounded untrusted model output or hidden data;
- a `REPO_LOCAL_PUBLIC_REVISION_TRIAL` event is written within
  the same existing authority/grant transaction;
- it consumes one of the **three total parent-task generation slots**,
  even when no Docker test is necessary;
- the next model request, if a slot remains, receives a structured
  `latest_rejection` describing the invalid hypothesis, exact
  SHA and explicit request to produce a different full-file algorithm;
- on this verified retry only, the local model's temperature changes
  from reproducible 0 to bounded 0.35 to permit exploration. The
  generated output remains untrusted and is still admitted solely
  by file allowlists, Docker PUBLIC tests, separate sealed reviewer,
  authority revision and source fingerprint checks.

Thus a repeated prompt no longer immediately terminates after the
first duplicate, while repeated or malformed generations CANNOT
result in unbounded extra model calls or cloud billing. After the
budget is exhausted the system abstains. Positive PUBLIC evidence
may freeze a linked `NEEDS_REVIEW` child, **never** approve a patch
or promote code to production.

## Independent verification

The expanded `tests/test_p13_public_refinement.py` proves:
- one duplicate followed by a genuinely different PUBLIC-passing
  test candidate can freeze an independently reviewable child;
- repeated duplicates across multiple calls consume at most three
  stored slots and do not produce new work or source changes;
- three malformed proposals also consume the full budget;
- prompt temperature differs only after verified duplicate evidence.

The real Docker P15 smoke and independent hidden-test boundaries
remain unchanged. The unmocked P16 3B experiment must use the same
previous fixed P14 two-task set with exactly the same hidden gold
digest `0357e22e8b567939b5f9b05baddb4acde1619055e9ed2250d3c715515f1e2baf`.
The expensive local-model CI opt-in is temporary and must be
removed after its result is observed. If 3B still gets 0/2,
that is a measured MODEL QUALITY FAILURE, not an infrastructure
acceptance, not a reason to fake a patch or widen access to hidden
labels. This is a bounded search improvement, not general
autonomous understanding.

**Remaining boundaries:** the local owner Windows 11 machine has
never been touched; no human reviewer-signed real business result
exists; fixed benchmark remains a tiny sample, and a 3B code model
cannot be promoted to a production autonomous developer on
0/2 evidence. Draft PR #12 remains unmerged; no paid LLM
API or finite trial/credit services were invoked.
