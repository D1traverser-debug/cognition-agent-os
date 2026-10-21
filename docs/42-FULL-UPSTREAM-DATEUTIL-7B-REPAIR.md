# P31 — External python-dateutil FULL-WHEEL code repair experiment

## Scope and governance

Independently reported real issue: [dateutil/dateutil#1588](https://github.com/dateutil/dateutil/issues/1588), RFC 5545 monthly `BYDAY` mixes unqualified and ordinal weekday entries (e.g. `MO,1FR`). Unmodified published python-dateutil **2.9.0.post0 (2024-03-01)** is an issue-preceding original source; model may not alter this wheel on disk, target external upstream, owner's Windows PC or protected `main`. This is Draft PR #12 candidate-only. No cloud/paid or finite-credit inference.

**P31 aims to improve evidence quality relative to P21–P24**: it imports the **entire original upstream distribution wheel**, plus the actual independent `six` dependency, in an actual **network-disabled, read-only, unprivileged Docker** Python 3.12-Alpine process. It invokes the original `dateutil.rrule.rrulestr`, original related modules and dependency; no extracted-method adaptation and no mock parser. Original wheel is downloaded read-only by CI from PyPI with `--require-hashes` and SHA256 checked again in the Python test. Original package is NOT executed on the GitHub Actions host. Other source files remain intact. Note: even successful one-file patched full-package execution would NOT be a "multiple source files edited" result or upstream maintainer acceptance.

## Frozen original materials and independent gold

- Original `python_dateutil-2.9.0.post0-py2.py3-none-any.whl`: SHA256 `a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427`.
- Real dependency `six-1.17.0-py2.py3-none-any.whl`: SHA256 `4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274`.
- Reporter issue: `https://github.com/dateutil/dateutil/issues/1588`. No public patch or answer is included in the prompt. Public issue/repo may nevertheless be present in model training; blind generalization cannot be inferred.
- PUBLIC **4** cases: mixed ordinary+ordinal weekday recurrence in April 2024 and leap February 2024; separate ordinary-only and ordinal-only controls.
- HIDDEN **8** independent cases: different months, year boundary, negative/positive ordinals and plain controls; dates independently calculated using **Python standard-library calendar** without invoking dateutil. No hidden test labels or answers appear in model input, image or runner process.
- Frozen manuscript manifest SHA256 `8e5db99800c505cbd2482fe74059df0831ca3237f084ffdc5d4fd68caae380b5`. Both cases and goal are embedded in `scripts/verify_p31_full_dateutil.py` with offline identity tests `tests/test_p31_full_dateutil.py`. No unreported case additions after generating a candidate.
- First actual original release Docker baseline at [Actions #39627357700](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39627357700): PUBLIC **2/4** and authentic original full-wheel import, hidden not tested, model not called. This is more realistic than a single extracted method, though the domain scope is still one recurrence subfeature.

## Candidate and independent acceptance

1. A real installed local-only `qwen2.5-coder:7b` on disposable GitHub Linux CI, opt-in marker `[run-p31-full-dateutil-7b]` only, exactly **one** Ollama `/api/generate` call, max **180 seconds**, no public feedback retry, no cloud fallback, no prepared correct patch. Model receives the behavioral goal, PUBLIC labels, and relevant ORIGINAL constructor/mask/filter excerpts (not 66KB full source).
2. The untrusted model must return a compact JSON `edits` list (1–3 unique exact literal replacements, tightly size bounded). Deterministic expansion is against the actual immutable rrule module from the verified wheel. Separate AST comparison ensures that **only `dateutil/rrule.py::rrule._iter`** changed; no new imports/side effects/module edits, no whole-source replacement. Rejection is recorded as no candidate, not a semantically refuted patch.
3. Valid patch is rebuilt as a real published-wheel-compatible ZIP with corrected `.dist-info/RECORD` for the updated Python module. All other upstream and dependency source entries are verified byte-identical; the original published wheel SHA remains unchanged. The patched wheel is mounted read-only into the same isolated Docker runner with actual `six`; it is not installed on the owner system or pushed to upstream.
4. Independent PUBLIC outcome 4/4 is required to even open the separate sealed HIDDEN 8 cases. Only PUBLIC 4/4 and HIDDEN 8/8 would justify `isolated_repair_verified=True`, never a production/maintainer/full-suite claim. Any failed or missing model response must be logged without fake success or repeated tuning.

## Preflight evidence before the one genuine model attempt

The initial transport unit regression hit a real `ZipInfo` metadata aliasing error after a synthetic repack (`BadZipFile`). This was corrected by copying ZIP entry metadata before writing new archive entries. It has no bearing on external-model code repair. Final no-model [Actions #39628692197](https://github.com/D1traverser-debug/cognition-agent-os/actions/runs/39628692197) on `bb9206f2b7aa194b2044b5369bbbcfe399c8c416` **COMPLETED/SUCCESS**: Linux **349/349** including compact scope, exact-edit and real-wheel RECORD consistency tests; Windows offline, actual original full-wheel Docker baseline, native Windows Task Scheduler all PASS; optional 7B tasks SKIPPED. This preregistration-only documentation commit triggers exactly one opted-in measured test; marker is removed immediately after dispatch.

## Outcome

**PENDING ORIGINAL ONE-SHOT REAL 7B EVIDENCE.** Do not infer repair quality from this document, from CI success, or from source-code inspection. Record genuine generated candidate validity, PUBLIC/HIDDEN behavior, exact Actions run link, and status in a subsequent appendix; do not alter frozen gold or repeat a failed attempt. No deployment or merge permitted.
