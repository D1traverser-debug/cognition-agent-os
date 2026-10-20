# cognition-agent-os — durable continuation checkpoint

Checkpoint date: 2026-10-20. Repository: `D1traverser-debug/cognition-agent-os`. This file is a checkpoint, not an independently executing agent or permission to mutate production.

## Governing objective

Build a self-directed cognition/execution system that takes user outcomes and bounded authority, researches and challenges causal assumptions, acts, independently verifies results, discovers systemic failure classes, repairs and learns without relying on repeated user correction. Keep the system valuable to real tasks, not merely a software specification diff monitor.

Binding budget constraint: no remote LLM usage billed per token; no AI trials, limited free credits or paid services. Default deterministic, model calls zero. An existing optional installed local Ollama model is allowed only when explicitly configured and cannot approve its own conclusions. The user's Windows 11 computer is the candidate host, not assumed deployed.

## Exact repo topology and fresh evidence

- `main`: legacy initial README only; NO P1/P2 promotion.
- Draft PR #1: architecture baseline.
- Draft PR #2: SQLite/task/grant/evidence worker prototype.
- Draft PR #3: local-only Ollama option, public source smoke, CI; head branch `feat/free-local-inference-20261020`.
- Draft PR #4: P2 Windows local host tick and durable resume; head branch `feat/local-scheduled-host-20261020`; base is PR #3 branch. URL: https://github.com/D1traverser-debug/cognition-agent-os/pull/4
- Verifiable CI for P2 before this checkpoint commit: run `39412342231`, job `118592922230`, `31 tests in 3.277s; OK`, real immutable public GitHub source smoke step PASS, associated with commit `c31848131b34fa1fa892a39c8995e6d2f5fb78d0`. New commits require new CI checks.

The actual P2 code adds `host-tick`, bounded queue draining, refused unseeded host authority, durable `host_ticks` local observations, test coverage for new process restart / no duplicate replay / missed tick / retained revocation, no-install entrypoint and an explicit-opt-in Windows Task Scheduler registration script. Docs: `docs/07-LOCAL-HOST-RECOVERY.md`.

## Verified vs not verified

VERIFIED IN GITHUB ACTIONS: 31 Python tests, real pinned public source read smoke. The developer's container Python syntax check is additional limited evidence. CI does not prove a Windows task was installed or truly woke after the chat closed.

NOT VERIFIED: a real Task Scheduler registration or unattended tick on the user's PC; independent task intake; actual locally installed LLM weight execution/quality; surprise-risk identification; competing causal theory validation; semantic or business holdout; autonomous issue repair and promotion; always-on host availability; end-to-end outcome acceptance. A static pinned pair on a recurring task repeats the same observation — it is not a live repository watcher.

## Next causal/execution priorities (in order)

1. Re-read current PR #4 head and Actions evidence. If new CI is green, keep changes in draft until physical deployment evidence; do not report autonomy finished.
2. After owner explicitly installs local host on Windows, verify independent Task Scheduler history + SQLite `host_ticks` + user-independent overdue task advancement. If no OS access, do not pretend this occurred; continue independent offline implementation/testing instead.
3. Build real **changing** source ingestion on an immutable-snapshot checkpoint scheme (branch/ref observation must resolve immutable SHA, anti-replay and authorization needed). Prove changed/unaffected cases before assuming polling is useful.
4. Add outcome-grounded semantic judgments and an independent holdout oracle before any autonomous solution promotion. Study other task families to prevent one-demo architecture.
5. Only then implement bounded autonomous goal decomposition, systemic causal repair and post-change observation. No broad-purpose agent is complete until real held-out task outcomes are proven.

## Continuation contract

Recover parent reference from `D1traverser-debug/universal-agent-os@main:ENTRYPOINT.md` and `CURRENT_SYSTEM.json`; current independent project repository is the owner of cognition-agent-os project code and candidate evidence. `uaos-controller-runtime` is a behavioral dispatcher, not verifiable native ChatGPT interception. Respect candidate branch → PR → owner CI → controlled promotion → reread. Reassess the actual outcome before choosing next work; use current repo evidence over memories or this checkpoint if inconsistent. Never treat a PR, synthetic fixtures or model self-rating as independent evidence of real autonomy.
