# Broad failure-space discovery, including unknown unknowns

This map is a **lens**, not a claim that every possible future issue has already been listed. The existence of a category does not prove it occurred. For new or repeated problems search other layers even after finding a plausible local explanation.

| Layer | Plausible mistake | Disconfirming probe |
|---|---|---|
| Need and acceptance | The user's proposed API edit is treated as the true goal | Recover actual observable behavior, alternative unchanged API, missing constraint and reviewer oracle |
| Entrypoint/activation | New function is written but ordinary CLI/Host never calls it | Follow exact route and execute fresh installed entrypoint |
| Local algorithm | First failure stack line is the root cause | Reproduce, alter upstream precondition, compare competing causes |
| Integration/callers | Local test passes, dependent version breaks | Contract test, old and new users, rollback, source authority |
| Domain/ownership | Change lives in wrong bounded context or creates second owner | Context map, data/effect authority, no duplicate controller/ledger |
| State/lifecycle | Retry repeats same method; crash replays effect | State transition and fault-injection test with durable receipt |
| Model reasoning | Valid JSON/quote treated as correct conclusion | Contradictory evidence, abstention, paraphrase, false citations, class confusion |
| Evidence context | Source preview hides late crucial text | Full-document targeted reads, swapped evidence order, conflicting sources |
| Security | Untrusted document/model claims new grant | Validate original authority at actual write boundary, source swap after audit |
| Environment | Only Linux CI is green | Windows/native CLI/Docker/prod-like entry and version compatibility |
| Evaluation | Agent's own test defines and endorses its success | Independent source-oracle, unknown holdout, false-positive and negative reporting |
| Evolving scope | Old fix works on one test, breaks new requirement | Adversarial constraint change and architecture walkthrough |
| Knowledge transfer | Successful technique becomes universal recipe | A different-task fit/non-fit experiment compared with no-memory baseline |
| Complexity/cost | Every problem runs giant all-web research or never investigates enough | Risk/unknown-triggered depth and evidence saturation, not fixed token/step quota |

Cross-layer probes: user provides plausible but wrong approach; requirement changes after plan; one source is stale; syntax passes but behavior never activates; false answer has a real quote; changed credential/revocation; interrupt between durable steps; old API consumer remains; counterexample invalidates initial causal theory.

**Unknown category:** proactively inspect domain/source taxonomies, adjacent professional practice, architectural boundaries and failure injection classes. Record new issues as unknown instead of forcing a known error code, then investigate the causal mechanism. Exhaustive prediction of future failures is impossible; the search method must be able to learn new categories.
