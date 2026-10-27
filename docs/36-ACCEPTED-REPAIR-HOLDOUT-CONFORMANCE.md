# P25 — Accepted repair holdout-evidence drift: independent re-attestation and enforceable containment

## Outcome and authority

Candidate-only experiment in `D1traverser-debug/cognition-agent-os` Draft PR #12; main remains unchanged and no owner Windows installation, paid/finite-credit model inference, external upstream write, or release is permitted. The goal is systemic self-governance in the EXISTING ledger/host effect path, not a standalone passive monitor.

**Finding**: P24 showed why claims and execution observations can diverge. P25 inspected the existing `conformance.py` enforcement and all three repair families. `pure_code_repair` (`audit_patch`) and `pipeline_code_repair` (`audit_pipeline`) re-read current holdout bytes and recheck gold before honoring verified-state claims. The `repo_container_repair` post-acceptance `audit_repo(require_staged=True)` previously compared only original source, public bytes, staged patch and a historical `REPO_DOCKER_HOLDOUT_ACCEPTED` receipt, but never read the **current sealed gold bytes**. After an actually accepted repaired task's hidden fixture was replaced/deleted, it could still be stamped mechanically valid. This is a materially unsupported positive ledger claim, not an observed software-model semantic failure.

## Two independently falsified defects

**Failure A — missing gold re-attestation.** In a temporary SQLite ledger, create a legitimate `repo_container_repair` task; accept its deterministic proposal with independent mock Docker boundary; verify `REPAIR_LAB_VERIFIED`, preserved original source, immutable artifact/staged patch and genuine shape of the historical holdout receipt. Then corrupt or delete `hidden.json` without changing the accepted candidate or historical receipt. The old post-acceptance audit could not detect any changed holdout. Fix: `src/cognition_agent_os/repo_repair.py::audit_repo` now checks `safe_fixture(fixtures,spec["holdout"])` and its SHA256 against `spec["holdout_sha256"]` when **and only when** `require_staged=True`. It refuses on changed or absent bytes using the existing `HOLDOUT_PIN_MISMATCH` failure. The planner-facing default audit intentionally **does not** read gold; no hidden answers enter model prompts.

**Failure B — semantic error in existing governance routing.** First fault-injection CI [#39604850524](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39604850524) was RED: even after the underlying `audit_repo` started returning `HOLDOUT_PIN_MISMATCH`, `conformance._check_one` classified the reason as `INSUFFICIENT_EVIDENCE` rather than `CONFIRMED_INCONSISTENCY`. The enforcing controller therefore retained `REPAIR_LAB_VERIFIED` and did not trip repair capability. This demonstrates why local detection alone does not constitute self-governance.

Fix: for an **already accepted** `REPAIR_LAB_VERIFIED` task, `HOLDOUT_PIN_MISMATCH` is treated as a confirmed contradiction; still insufficient for unrelated unreviewed states. The existing `_quarantine` and `CRITICAL_REPAIR_LAB_BREACHES` mechanisms revoke the false state and persistently disable only `pure_code_repair_lab`. Independent next-task test confirms that restoring original hidden data does **not** silently re-enable the circuit; subsequent review refuses `CAPABILITY_DISABLED` before entering Docker, until separately authorized re-acceptance. No automatic global release or owner machine effects.

## Negative and positive evidence

Two temporary-ledger fault injection cases in `tests/test_p12_repo_lab.py`:

- Replaced gold after legitimate acceptance: read-only conformance flags `HOLDOUT_PIN_MISMATCH` without mutating the ledger. Enforced conformance revokes the earlier state to `UNKNOWN`, records exactly one `CONFORMANCE_CAPABILITY_DISABLED` receipt, and opens the repair circuit. A later new repair is blocked even after gold restoration, and Docker is NOT called.
- Removed gold after acceptance: independent audit finds the same violation; enforcement revokes positive state and trips capability.

Positive controls: exact unmodified gold continues to yield `REPO_BYTES_MECHANICALLY_VALID`; planner-side pre-review `audit_repo(require_staged=False)` intentionally does not inspect holdout, preserving secrecy. Existing other repair-family admission and cross-platform suites remain unchanged.

The final logic with next-task refusal passed actual ordinary [GitHub Actions #39605720212](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39605720212) on HEAD `578214d9884db14ed318513d228c11b31682f5e1`: Linux 330/330 tests, Windows offline regression, genuine Docker integration and GitHub-hosted Windows native user-scoped Task Scheduler all SUCCESS. No model inference was triggered, experimental model jobs SKIPPED. The first red run remains part of failure evidence; do not claim it was already green.

## Boundaries

These are fault-injection governance tests using genuine temporary SQLite and filesystem state with a mocked Docker *execution boundary*; they are not a claimed external-model semantic acceptance or full integration of P24 finance source. The independent repo Docker integration in ordinary CI is separately real. The post-acceptance audit verifies actual sealed gold identity and historical receipt, not repeated Docker execution of every hidden test at every runtime poll. Semantic regression or unknown correctness on outside repositories is not proven. An adversary with unrestricted access to mutate the SQLite ledger **and** all gold/origin bytes can compromise local evidence; this mechanism does not claim hostile-host integrity.

Next: verify the **post-archive candidate HEAD** with normal Linux/Windows/Docker/Windows Scheduler and local model SKIPPED; record final post-commit witness as a PR comment instead of generating an unbounded series of commits. Continue testing other claim/effect contradictions across the integrated runtime and wider real-repository evidence, not another monitoring-only subsystem.
