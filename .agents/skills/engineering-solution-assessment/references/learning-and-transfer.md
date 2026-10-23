# Knowledge acceptance and transfer

Knowledge entries are *candidates*, not instructions that gain authority by being added to a file.

1. Record the **actual trigger** and original requirement/source; do not rewrite the historical question to fit the technique chosen.
2. Record competing explanations and alternative methods, plus a *disconfirming* observation. Include cost, interface and recovery consequences.
3. Trace implementation into the real caller and check the target outcome separately from a passing regression.
4. Write the observed **FIT conditions** and **NON-FIT conditions** for every retained method. "Always do DDD" and "never refactor" are untested generalizations.
5. Re-test the learned choice on another task, with a new source, entrypoint or constraint. Compare to a baseline that does not use the learned card. If it does not improve the actual outcome, downgrade confidence or document incompatibility.
6. Update only the existing owner-authorized knowledge/evolution lifecycle after independent evidence. Do not create a parallel learning database, scheduler or approval authority.

The candidate entries are in `knowledge/engineering-methods/method_cards_v1.json`. A successful reuse and independently checked real outcome is the key evaluation; number of method cards, tokens, prompts or CI tests is not.

External source freshness matters. A method's documentation can be revised and the system's own architecture can change; a stale recipe may become a wrong intervention.

### Negative experiences that must stay visible
- PR #28: source citation existed while model chose an irrelevant/injected source. Mechanical source integrity was not semantic relevance.
- PR #29: assistant-authored labels initially treated "unanswerable" as "no relevant evidence", contaminating the metric. Labels were corrected before later runs; this was not pristine holdout truth.
- PR #30: BEIR external qrels exposed missing ArguAna corpus IDs; integrity exception needed explicit accounting, not a quiet pass.
- PR #31–32: larger local model improved abstention/rationale, but whole-abstract contradiction discrimination remained poor; changing JSON Schema enum order caused zero flips. Simple prompt/label reordering is not an evidenced fix.
- PR #33: different mechanically valid methods were not necessarily satisfying a shared owner goal; the fixed exact-record postcondition improved that **specific local capability**, not general problem solving.

These are evidence pointers from current candidate PR histories, not promoted proof of a general reusable cognitive method. A future task must show actual transfer.
