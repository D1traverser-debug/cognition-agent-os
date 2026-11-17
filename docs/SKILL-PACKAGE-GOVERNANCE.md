# Shared Skill package capacity governance

Status: CAOS engineering contract, version 1.0.0.
Applies to every active SKILL.md entrypoint and its declared package in this repository; the same contract is reusable by child repositories through the composite GitHub Action below.
Does not claim native ChatGPT/Codex activation, correct model behavior, permission to mutate a child, or owner/business acceptance.

## 1. Failure class and root cause

The recurring failure was not simply an oversized file. The common mechanism was that each local repair appended more policy and domain detail to the Skill entrypoint, while package checks covered only selected entrypoints. In this repository the ChatGPT intake Skill was 8,896 UTF-8 bytes, but the active Codex goal-grounded-semantic-review/SKILL.md was 13,533 bytes. Existing tests enforced a size check on the ChatGPT entrypoint only and did not inventory all active Skills. The local test therefore gave a false sense of repository-wide coverage.

A second failure mode is duplicate policy: the same rules are copied into entrypoints, CI snippets and handoff prose, then one copy changes without the others. The contract below makes the budget, active entrypoint inventory and package file closure explicit and machine-checked.

## 2. One shared budget

config/skill_package_policy.json is the repository's machine-readable policy source.

| Measure | Limit | Meaning |
|---|---:|---|
| Platform entrypoint ceiling | 12,000 UTF-8 bytes | Absolute external ceiling; never raised without first-party platform evidence |
| Operational entrypoint budget | 10,500 UTF-8 bytes | CI hard-fail threshold; preserves 1,500 bytes of safety margin |
| Preferred entrypoint budget | 9,000 UTF-8 bytes | Target; above this, CI reports a warning |
| Reference module ceiling | 32,768 UTF-8 bytes | On-demand reference bound, separate from the entrypoint limit |
| Package uncompressed ceiling | 131,072 bytes | Bounds the declared package closure |

The limit is measured from canonical UTF-8 bytes with CRLF/CR normalized to LF, not characters, line count, token estimates, or rendered size. Linux and Windows therefore produce the same byte count and package payload. Multi-byte Chinese text is counted correctly. BOMs, invalid UTF-8, symlink escapes, missing references and undeclared active Skills fail closed.

## 3. Correct information architecture

A Skill entrypoint is a discovery and execution router. It should contain only:
- scope and trigger conditions;
- role and authority boundaries;
- essential invariants that must be present on activation;
- a short decision/continuation contract;
- explicit links to on-demand reference modules;
- the route to the shared maintenance and acceptance contract.

Detailed domain procedures, research atlases, long examples, evaluation corpora, tool lifecycle instructions and historical evidence belong in separately named references or source-of-truth documents. Load them only when the task requires them. A reference file does not count toward the 12,000-byte entrypoint ceiling, but it must be declared, exist, stay within its own bound and be included in the package when the client needs it.

Do not solve an over-budget failure by blindly deleting important constraints, minifying prose, moving everything into one giant reference, or increasing the cap. Preserve semantic obligations and test that the entrypoint points to the correct module.

## 4. Mandatory edit lifecycle

For every create/edit/move/delete of an active Skill or its references:

1. Read the current owner goal and relevant corrections; identify the exact active client entrypoint(s), package manifests and references.
2. Inspect exact UTF-8 byte counts before editing. Compare the proposed architecture: keep essential routing/invariants in the entrypoint; move detailed content to the smallest appropriate on-demand modules.
3. Update the policy inventory when an active Skill, package or reference is added, retired or moved. Do not list archive/history as an active entrypoint.
4. Run python scripts/verify_skill_package.py. This scans all declared roots, rejects unregistered active SKILL.md files, checks byte budgets, frontmatter, reference closure, symlink safety and package size.
5. Build the real declared package with --package <id> --zip-output <path>; read back exact ZIP membership and bytes. Do not rely on a hand-maintained second list.
6. Run focused semantic tests, negative mutation tests and exact-HEAD CI. Verify that required behavior was preserved across the new reference boundary.
7. Report source changes, byte counts, package readback and remaining native activation/owner outcomes as separate evidence.

The check runs before and after changes in CI. A green source/package check is engineering evidence only; it is not proof that a native client selected the Skill or that a real owner outcome succeeded.

## 5. Cross-repository reuse

CAOS exposes a dependency-free composite action at:

integrations/github-actions/skill-package-budget/action.yml

A child repository keeps its own Skill, domain authority, references and local config/skill_package_policy.json. Its CI invokes the action using a pinned CAOS commit SHA:

    - uses: D1traverser-debug/cognition-agent-os/integrations/github-actions/skill-package-budget@PINNED_CAOS_COMMIT_SHA
      with:
        policy-path: config/skill_package_policy.json
        report-path: skill-package-report.json

The action only reads the checked-out child workspace and runs a standard-library Python validator. It does not call a CAOS runtime, access a child provider, change business state or grant permissions. Each child remains the owner of its own policy inventory and CI adoption. A child is not considered protected merely because this action exists in the parent repository; the action must actually run in that child's CI on its own active Skills.

When adapting the policy, preserve the shared 12,000 / 10,500 / 9,000 byte thresholds. A child may choose a stricter operational budget, never a looser one. Do not create a second task ledger or parent runtime dependency.

## 6. Acceptance and falsifiers

The implementation must reject:
- a Skill whose character count is below 12,000 but whose UTF-8 byte count exceeds the operational budget;
- an active SKILL.md omitted from the policy inventory;
- a declared but missing reference;
- a package missing a required entrypoint or reference;
- a symlink/path traversal escaping the repository;
- an entrypoint above the platform ceiling even if a local policy tries to permit it.

It must accept:
- all active CAOS Skills below the operational budget;
- an on-demand reference larger than 12,000 bytes but below its separate reference limit;
- archived Skills excluded from the active inventory;
- a package whose ZIP readback exactly matches its declared files.

A regression in any of these cases reopens the shared package contract, not merely the one file that failed.
