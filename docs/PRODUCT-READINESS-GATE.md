# Integrated product readiness gate — snapshot 2026-10-24 (development PR #36)

**Current disposition: NOT_READY for unattended autonomous use.** Green CI is component evidence, not business outcome, deployed host, or autonomous planning evidence.

**Source/version caveat:** these six acceptance gates are a **current engineering evaluation model**, not the same identifier namespace as archived owner-source ConOps G1–G8. The inherited R01–R24/OT01–OT14 inventory is marked DRAFT/NOT_STAKEHOLDER_APPROVED in `evaluation/assurance_registry_v1.json`. Later user corrections and tested architectural decisions must be traced, not overridden with a frozen old proposal. Actual design authority rests with current user objectives, delegated scope, implemented source/host state and independent provider results; no PR or model self-declaration grants permission.

**Branch and evidence:** latest code-tested root at snapshot `962ee4e560972d3cc1f47bddf1b6986b17d2c011` (PR #36; full recursive tree 188 files). [Actions #40050033744](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/40050033744) passed real Linux/Windows local CI; optional model/provisioner experiments skipped. Every subsequent commit must recheck its own matching HEAD CI before calling it tested.

## Required single-system acceptance

1. **Goal -> choice:** Given a registered goal, bounded budget, legal grants and at least two registered capabilities, the common controller independently selects the next task. An adverse independent verdict causes a *different* authorized plan to be selected and durably admitted without a new chat prompt.
2. **Choice -> execution -> revision:** The newly selected task actually runs in the same task ledger. Independent readback changes the original goal's decision on the next tick. Repetition, no-progress and budget exhaustion halt safely.
3. **Unattended host:** A real external trigger invokes host ticks repeatedly while the user is absent; restart preserves lineage and avoids duplicate effects.
4. **Conformance and safety:** Scope, revocation, policy, lease fencing and attempt budgets are enforced at effect boundaries. Independent conformance finds systemic failures, creates constrained repairs, verifies impact across sibling paths, and requires legitimate promotion authority.
5. **Generalization:** Two materially different held-out task domains pass this *same* control-loop test without domain-specific controller branches. A production test evaluates owner-meaningful outcomes, not just hashes.
6. **Evidence attribution:** Every acceptance claim links specific executed artifact, authority, evaluator, host trigger and independent effect; unverified is not pass.

## Evidence at this revision

- Installable `cognition-os` CLI and durable SQLite task ledger: VERIFIED as a bounded prototype on ephemeral Ubuntu and Windows CI; database is created by explicit `init`, not by `status` or a missing-path seed. This is not installation on the owner's machine.
- Deterministic registered task execution and independent mechanical checks: PARTIALLY INTEGRATED.
- Independent **local** negative-outcome -> bounded second preauthorized alternative -> admitted child -> execution -> subsequent mechanical verification: **IMPLEMENTED FOR TWO FIXED DOMAINS, NOT A GENERAL OUTCOME CONTROLLER**. Current JSON/CSV and record-reconciliation adapters still contain domain-specific decisions; neither new method discovery nor external business-outcome acceptance has been shown.
- Existing PR24→PR25 architecture A/B: seven reproducible local scenarios × three runs, unchanged terminal-state behavior and stable traces, **PASS**; does not establish optimality or general autonomy.
- Official Graphify structural path check: **PASS** for call-edge inventory, not semantic comprehension; AOCI official bootstrap has zero model-authored entries, index not aligned.
- Current candidate cross-platform installation: **PASS** on Ubuntu and Windows via independent venv, with revoke persistence and malformed-DB refusal; not approval to deploy.
- Real user's unattended long-lived deployment: **NOT VERIFIED**.
- Multi-domain outcome-based held-out generalization: **NOT VERIFIED**.
- End-to-end self-governance including authorized promotion and recurrence prevention: **NOT VERIFIED**.

### Additional evidence from the currently stacked integration branch

- **One local controller, not seven speculative agents:** current `ledger.py`, `control_kernel.py`, `host.py`, `runner.py`, domain adapters and `outcome_feedback.py` share SQLite task, grant and event lifecycle. This is a verified *implementation feature*, not proof of an open-ended cognitive operating system.
- **Knowledge and research:** `knowledge_routing.py`, `research_gap.py`, `research_assessment.py`, `investigation.py` and optional local model adapter support bounded, pre-registered or source-pinned research. They do **not** establish unrestricted unknown-source credibility, novel method learning and autonomous scientific validity. Previous genuine model trials and negative results are preserved in docs/25–45 and independent PR #29–32.
- **Owner-target correctness:** PR #33 v2 fixed shared-target checking before candidate acceptance; PR #36 v3 adds an explicit **local sandbox-effect** required flag and independent post-effect readback through the original host/worker, with tamper and fresh-source rechecks. Successful synthetic file outcome is **NOT owner-meaningful external business effect**, including when separate fixture oracle agrees.
- **File safety:** PRs #34/#35 use one POSIX dirfd-anchored read/staging owner and test sibling mutation entries. Hostile shared mutable-directory Windows write safety remains a specific release blocker; skipped Windows attack tests cannot count as PASS.
- **Host continuity:** hosted ephemeral Windows Task Scheduler and cross-process SQLite restart demonstrate a valid test environment, **not** deployment/uptime on the owner's PC nor native ChatGPT chat-session connection.
- **Unproven capability gate:** no personally authorized provider mutation/readback, unknown ACK transaction guarantee, real cost ledger, representative held-out cross-domain method discovery, cumulative user correction-load measurement or approved system-wide promotion. All six product acceptance gates remain **OPEN**.

## Immediate implementation order

The remaining product blockers are qualitatively different from fixing the packaging:
1. Freeze an owner-specific, independently measurable real business objective and permission contract. Validate real external effect readback with an independent checker not authored or controlled by the planner.
2. Under identical models/budgets and blinded task sets, compare raw-repo context versus Graphify, genuine model-authored AOCI, and AOCI+Graphify. Reject tooling that increases stale-context or maintenance failures without improving correct outcomes.
3. Test new, previously unknown task types and causal alternative selection across at least two materially different real domains. Track objective completion, permission denials, repeats, negative transfer, latency and human corrections.
4. Only after the above, verify original OT06 new-chat continuity against the live authoritative state and real owner-device unattended operation. Hosted CI scheduler is not a substitute.

Keep the current integration stack PR #26→#27→#28→#33→#34→#35→#36 in Draft, and preserve PR #29–#32 as a separate experimental evidence branch; old PR #25 is historical architecture evidence. Check exact live PR head/CI before using these dated references. Do not treat the initial local `init` write flag as a user-approved remote production grant.

**Release rule:** Until all six gates have end-to-end evidence on the same system candidate, the project must not be described as a usable autonomous OS. Do not conflate GitHub Actions with a deployed controller. Draft branches must not be merged or deployed implicitly.
