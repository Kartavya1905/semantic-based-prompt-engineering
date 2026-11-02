# Datasheet: ticket_triage golden dataset v1.0.0

## What it is

60 support tickets for a fictional business software platform, each with an agreed correct
triage answer: category, urgency, escalation and entities, plus a reference summary. It is the
answer key the benchmark (Phase 6) scores every prompt variant against.

| File | Role |
|---|---|
| `v1.jsonl` | The cases, one JSON object per line |
| `v1.manifest.json` | Frozen SHA-256, version, annotation status and coverage counts |
| `ANNOTATION_GUIDELINE.md` | The labelling rules every annotator follows |

## Provenance

- **Source:** hand-written synthetic tickets. No real customer data. Products (DataSync,
  ReportBuilder, TeamChat, Insights Dashboard) and all identifiers are invented.
- **Labels:** written by one annotator (`claude_draft`) following the guideline.
- **Annotation status:** `draft_single_annotator`. Not yet double-annotated (see "Next steps").
- **Leakage rule:** no case may copy or closely paraphrase a few-shot example from
  `prompts/fragments/`; a test enforces this.

## Splits

| Split | Cases | Use |
|---|---|---|
| `dev` | 36 | Prompt iteration. 11 cases are tagged `smoke` for fast CI runs. |
| `test` | 24 | **Held out.** Run only at milestones, never while editing prompts. |

Every category, every urgency level and every key slice (injection, non-English, security,
legal/deletion, missing info, multi-issue, very long, rule order, ambiguous) appears in both
splits. Exact counts are in `v1.manifest.json`.

## Known limitations

- **Small.** With 60 cases, an accuracy of 80% has a 95% confidence interval of roughly
  ±10 percentage points (±13 on the 24 test cases). Measured in Phase 7 (2026-11-02): on the
  36 dev cases, a paired comparison only detects differences of about ±22–26 points with 80%
  power. Confirming a 10-point gain needs ~220 paired cases (15 points: ~96; 20 points: ~53).
- **Too few critical cases to test critical recall.** Each split has 5. With 5 cases even a
  perfect 0/5 → 5/5 improvement gives an exact McNemar p of 0.0625, so it can never pass
  p < 0.05; at least 6 (realistically 20+) critical cases per split are needed.
- **Single annotator.** Labels reflect one reading of the guideline until a second person
  annotates blind and disagreements are adjudicated.
- **Synthetic.** Hand-written tickets are cleaner and shorter than real ones.
- **Skewed towards technical.** 28 of 60 cases are technical, which mirrors real support
  queues but leaves few `other` (3) and `feature_request` (4) cases, so per-class scores for those
  are noisy.
- **One deliberate `policy_gap` case (TT-0012).** Its label follows guideline clarification C1,
  which the prompt does not state.

## Next steps

1. **Second annotation (blind).** A second person labels the tickets without seeing these labels:
   `python -m evaluation.annotation_agreement export evaluation/golden_datasets/ticket_triage/v1.jsonl annotator_b.csv`
2. **Measure agreement:** `python -m evaluation.annotation_agreement compare … annotator_b.csv`.
   Target Cohen's kappa ≥ 0.7 per field. Below that, improve the guideline first.
3. **Adjudicate** each disagreement, update labels, add the second annotator's id, bump
   `dataset_version` to 1.1.0, and re-freeze with `--annotation-status adjudicated`.
4. **Grow** towards 200+ cases, especially `other`, `feature_request` and real-world-style
   long tickets.

## Change rules

Any edit to `v1.jsonl` changes its hash, and the dataset test fails until the file is re-frozen:
`python -m evaluation.freeze_golden_dataset evaluation/golden_datasets/ticket_triage/v1.jsonl`.
Bump `dataset_version` in every line whenever labels change. Benchmark results record the hash,
and results from different hashes are never compared.
