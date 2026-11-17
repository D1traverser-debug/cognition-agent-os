# Research, method selection and requirement decomposition

Load this module when the task has an unfamiliar method, material architecture choice, repeated failure, research gap, conflicting requirements or an unclear acceptance contract. It is not a default-loaded prompt.

## Discover, verify and select unfamiliar methods

Use a source-discovery funnel scaled to the unknown; do not turn it into a fixed service-call quota.

1. Translate the owner's actual missing capability or failure invariant into multiple searches, including alternate project names, source categories, counterexamples, migration and security terms. Start from first-hand local entrypoints and failure evidence, not the last tool or vendor mentioned.
2. Discover candidates, not truth: relevant GitHub repositories/releases, official registries, package indexes, trend lists and practitioner discussions may reveal leads. Record exact post, date, author and link when accessible. Stars, downloads, endorsements, demos and search rank are weak discovery signals, never correctness, permission or safety evidence.
3. Verify the actual mechanism: canonical repository and license, current tagged release, implementation, API/tool schemas, official docs, reproducible tests, unresolved issues, vulnerabilities, maintenance, migrations, failure modes, deployment/authentication and cost. Distinguish reference servers from production capabilities, retrieval from durable memory, code graphs from semantic evidence, and source hashes from truth.
4. Compare real pathways against the same failure and owner outcome: existing tool/interface, adapt a mature implementation, replace a deficient component, add a narrowly authorized adapter, or abstain/research further. For each viable option specify what it replaces, composition with current authority/grants/state, source/version provenance, failure and rollback, usage/hosting cost, and a falsifier.
5. Test before promoting reusable knowledge: use an isolated frozen baseline with an unseen relevant case, counterexample and unchanged-evidence/retry case. Compare independent owner-level outcomes, cost and regressions, not model opinions. Record applicability, competing explanation, verified result, rejected candidate and reopen condition in the existing work evidence. Never create a second parent memory or permanent dependency just to record research.

For actual Agent/Harness design gaps or repeatedly failed research, use the pinned [Datawhale Agent-Learning-Hub primary-source atlas](agent-learning-hub-primary-sources.md) as a discovery map. Read only the relevant source implementation and its limitations. The atlas is not an executor, truth oracle, installation decision or substitute for field-specific standards.

## Ask four expert questions before proposing a material solution

1. **Omissions:** Which checks, hidden assumptions, conflicting requirements, failure conditions or alternatives would domain experts raise that the user and agent did not ask for? Separate necessary protection from ceremony.
2. **Primary sources:** Which original user utterance, actual specification, raw event/trace, independent business observation or original research supports each material claim? Inspect raw materials rather than derivative summaries.
3. **Methods and tools:** Which proven approaches apply? Examine official Skill conventions, context engineering, independent evaluation, requirements traceability, stateful/property testing, static analysis and current implementations as relevant—not as a rote checklist. Compare reuse, adaptation, deletion, replacement and new mechanisms against constraints and failure evidence.
4. **Independent falsification:** What could prove the selected plan wrong without trusting its author? Establish observable checks, external readback, negative controls, unseen cases, mutation/state-machine tests and authorized real outcomes as appropriate. State what available tools cannot prove.

## Decompose and trace requirements

For each in-scope behavioral requirement identify:

- Stable semantic ID, original source/location and owner status; never reuse an ID for a new meaning.
- Current/superseded/proposed/unknown status, temporal and domain scope, conflicts and explicit precedence.
- Preconditions, postconditions, prohibited transitions, invariants and lawful neighboring behaviors.
- Actual entrypoint, reachable call paths, state/effect authority, linked implementations and tests.
- Independent oracle, counterexamples, exact source revision, environment and negative/skip outcomes.
- Disposition: VERIFIED_IN_SCOPE, FALSIFIED, NOT_TESTED, SOURCE_MISSING, SPEC_UNDECIDED or EXTERNAL_VALIDATION_REQUIRED.

For repository-wide work, inventory the entire live tree and track individual behavior obligations, not one pass/fail per filename or SHA. Review docs and scripts as material sources too. Structural inventories do not prove semantic coverage.

## Decide the correct root-cause intervention

Fix the actual shared failure and satisfy the complete behavioral requirement. Compare materially different remedies where the choice matters—for example, original interface, compatible adapter, contract-preserving refactor, or removal. Evaluate effects on external contracts, neighboring legitimate tasks, stale knowledge and recovery. Do not create a standalone authority, agent or documentation ledger merely to satisfy audit formatting.

Preserve source history immutably where possible. Knowledge selection must not equate newest with true, matching words with applicable, archived text with authority, or a hash with entailment.
