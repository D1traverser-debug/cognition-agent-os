# P4 — pinned evidence reference gate (bounded, zero model credits)

## Governing goal and claim boundary

This is an **evaluation interface**, not the completed independent semantic oracle or an autonomous Agent. It separates an untrusted proposal from a reviewer-pinned reference data file, requires exact source quote provenance, and tests two **different task families**:

1. `protocol_impact`: streaming vs non-streaming contract change and unknown authentication migration.
2. `incident_triage`: integrity error, benign performance counter, incomplete reset recovery.

Both families include `SUPPORTED`, `REFUTED`, and `INSUFFICIENT` examples. The six sample statements and gold labels were **curated within this same development change** and are openly committed. Therefore they are **not blind / third-party-validated holdouts**. A model that has read the repository could see the gold labels. The result is a mechanical reference-agreement regression, not human-independent semantic truth.

## Trust boundaries

- Trusted reference digest must be supplied by a separate reviewer or approved external configuration as `--expected-pack-sha256`. It is a SHA-256 of the exact raw reference bytes, not a hash the model may declare for itself.
- `reference-export` sends only `case_id`, family, question, source text and SHA-256 source digest. The `gold` and `required_quotes` fields are excluded. In a deployment, the gold/reference file and expected digest must be held beyond the generator's read permissions; a public GitHub fixture does **not** establish this isolation.
- `reference-evaluate` reads a separately authored candidate JSON. A proposal cannot supply expected labels, overwrite reference quotes, alter the reference SHA or assert `grade=PASS`.
- Every case must cite verbatim evidence and match its source text SHA-256. A single decisive quote from a pre-curated reference must be contained within one cited span, and candidate outcome label must match the reference.
- This validates **mechanical reference agreement** only. A quote may be genuine but be interpreted incorrectly by both candidate and curation. Full reference agreement produces `REFERENCE_MATCH`, **never** `VERIFIED`, `COMPLETE`, independent semantic validation, approval or permission to mutate external/production resources.
- Inputs are bounded to 128 KiB with strict fields, complete six-case coverage and distinct families. Reference mismatch is `REFERENCE_MISMATCH`; missing/tampered packs or invalid candidate are `UNVERIFIABLE`.

## Offline demonstration without paid tokens

Use Python 3.10+ and the included `evaluation/curated_demo_reference.json`. The commands require the exact verified SHA-256 of that file, **pinned by a reviewer independently of the candidate model**.

```powershell
# Verify and retain the reviewed SHA-256 offline (demo only; not an external semantic review).
Get-FileHash .\evaluation\curated_demo_reference.json -Algorithm SHA256
# Substitute that checked expected digest in both commands:
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace reference-export --pack .\evaluation\curated_demo_reference.json --expected-pack-sha256 EXPECTED_64_HEX_SHA
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace reference-evaluate --pack .\evaluation\curated_demo_reference.json --expected-pack-sha256 EXPECTED_64_HEX_SHA --candidate .\runtime\candidate.json
```

`reference-export` prints a JSON object with the same `schema_version` and `reference_pack_sha256`, plus public cases; the generator must submit `answers`, one per `case_id`, with:

```json
{
  "schema_version": 1,
  "reference_pack_sha256": "expected 64-character hex digest",
  "answers": [
    {
      "case_id": "protocol_stream_transport",
      "label": "SUPPORTED",
      "citations": [{"quote": "text/event-stream is now mandatory", "evidence_sha256": "source text SHA256 from public case"}]
    }
  ]
}
```

The example above is **one answer only**, intentionally not a full valid six-case evaluation payload.

The two review CLI commands are read-only: they do not create or modify SQLite task/grant state, do not contact a cloud LLM, and cannot promote a candidate into the existing P0-P3 `VERIFIED` task state.

## Optional local-only candidate generation (already-installed Ollama)

P4 also adds `reference-propose-local`: it consumes ONLY the exported public
cases (no gold), requires a locally installed Ollama model from
`http://127.0.0.1:11434/api/tags`, sends a bounded JSON-classification
prompt to local `/api/generate`, and prints a candidate with strict schema.
It never auto-pulls models, never uses paid or cloud LLM APIs, and never
evaluates or authorizes itself. Network requests are fixed to the loopback
interface with redirects disabled.

```powershell
# Only after a permitted local model already appears in "ollama list":
python .\scripts\host_tick.py --db .\runtime\state.sqlite --workspace .\runtime\workspace reference-propose-local --pack .\evaluation\curated_demo_reference.json --expected-pack-sha256 EXPECTED_64_HEX_SHA --model YOUR_INSTALLED_LOCAL_MODEL > .\runtime\candidate.json
# Then invoke the independent read-only reference-evaluate command shown above.
```

Automated adapter tests use a mocked Ollama service; **no real model weights,
task transfer, or model quality have been verified**. The model still performs
internal inference tokens but does not consume billable remote tokens or
finite AI credits. True isolation of labels from a model with filesystem
access requires a separate trusted reviewer/host security boundary.

## Verification and negative controls

`tests/test_evaluation.py` exercises separate public input, a correct hand-filled reference agreement **harness positive control**, always-SUPPORTED candidate failing REFUTED/INSUFFICIENT cases, fabricated citation, correct citation with wrong source digest, wrong conclusion, tampered reference digest, duplicated/missing answer, untrusted self-grade, single-family collapse, no-network execution and CLI no-database side effect. Existing P0-P3 CI remains required.

## Remaining complete-outcome work

**Must not close P4 as independent semantic evaluation:** acquire source-competent *independent reviewer* gold (or an objectively executable external specification/behavior oracle), freeze it outside the candidate's read scope, collect actual model-generated predictions, execute **unseen** cases, then compare against the reference with separate acceptance evidence. A user-machine Ollama run has not yet been observed. No semantic promotion of parent UAOS or external writes.

A broader autonomous system additionally needs bounded goal decomposition, unknown-problem discovery, causal solution comparison, systemic repair, post-action observation, task-family transfer and true Windows unattended-host proof. These must not be replaced with more benchmarks or documents.
