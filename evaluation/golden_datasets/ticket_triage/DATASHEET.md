# Datasheet: ticket_triage golden dataset v2.0.0

## What it is

180 support tickets for a fictional business software platform, each with an agreed correct
triage answer: category, urgency, escalation and entities, plus a reference summary. It is the
answer key the benchmark (Phase 6) scores every prompt variant against.

| File | Role |
|---|---|
| `v2.jsonl` | **Current answer key.** The 60 v1 cases (unchanged labels) plus 120 new cases (TT-0061 to TT-0180) |
| `v2.manifest.json` | Frozen SHA-256, version, annotation status and coverage counts |
| `v1.jsonl`, `v1.manifest.json` | The original 60 cases, frozen and kept so results from 2026-11-01/02 stay reproducible |
| `ANNOTATION_GUIDELINE.md` | The labelling rules every annotator follows |

## Version history

| Version | Date | Cases | Why |
|---|---|---|---|
| 1.0.0 | 2026-11-01 | 60 (36 dev / 24 test) | First answer key |
| 2.0.0 | 2026-11-02 | 180 (108 dev / 72 test) | Phase 7 showed v1 was too small to confirm any prompt improvement: 36 dev cases only detect ~22-26-point differences, and 5 critical cases per split can never reach p < 0.05. v2 is sized for ~15-point differences (needs ~96 dev cases) and 20 critical cases per split. |

## Provenance

- **Source:** hand-written synthetic tickets. No real customer data. Products (DataSync,
  ReportBuilder, TeamChat, Insights Dashboard) and all identifiers are invented.
- **Labels:** written by one annotator (`claude_draft`) following the guideline. In the 120 new
  cases, `requires_human_escalation` was derived from policy rules 5-8 by code, not typed, and a
  test re-checks it for all 180 cases.
- **Annotation status:** `draft_single_annotator`. Not yet double-annotated (see "Next steps").
- **Leakage rule:** no case may copy or closely paraphrase a few-shot example from any file in
  `prompts/fragments/`; a test enforces this (text similarity < 0.6), and no two cases may be
  near-duplicates (< 0.8).
- **Written after seeing model results.** The new cases were written after the v1-v6 experiments,
  so their mix (more critical tickets, more "one function broken for everyone" near-misses) was
  chosen knowing where models struggle. They test known weaknesses on purpose; they were not
  written to favour any variant.

## Splits

| Split | Cases | critical | high | medium | low | Use |
|---|---|---|---|---|---|---|
| `dev` | 108 | 20 | 26 | 26 | 36 | Prompt iteration. The same 11 v1 cases are tagged `smoke` for fast CI runs. |
| `test` | 72 | 20 | 17 | 15 | 20 | **Held out.** Run only at milestones, never while editing prompts. |

Every category, every urgency level and every key slice (injection, non-English, security,
legal/deletion, missing info, multi-issue, very long, rule order, ambiguous) appears in both
splits. Exact counts are in `v2.manifest.json`.

## Known limitations

- **Still modest.** On 108 dev cases a paired comparison detects roughly 15-point differences
  with 80% power; confirming a 10-point gain needs ~220 paired cases.
- **Single annotator.** Labels reflect one reading of the guideline until a second person
  annotates blind and disagreements are adjudicated. This matters more now: one annotator wrote
  180 labels.
- **Synthetic.** Hand-written tickets are cleaner and shorter than real ones; only 6 are long.
- **Skewed towards technical.** 94 of 180 cases are technical, which mirrors real support queues;
  `feature_request` (10) and `other` (10) remain the thinnest classes, so their per-class scores
  are noisy.
- **Deliberate `policy_gap` cases (TT-0012, TT-0068, TT-0140).** Their labels follow guideline
  clarification C1 (a whole endpoint failing = outage), which the v1-v3 prompts do not state.

## Next steps

1. **Second annotation (blind).** A second person labels the tickets without seeing these labels:
   `python -m evaluation.annotation_agreement export evaluation/golden_datasets/ticket_triage/v2.jsonl annotator_b.csv`
2. **Measure agreement:** `python -m evaluation.annotation_agreement compare … annotator_b.csv`.
   Target Cohen's kappa ≥ 0.7 per field. Below that, improve the guideline first.
3. **Adjudicate** each disagreement, update labels, add the second annotator's id, bump
   `dataset_version` to 2.1.0, and re-freeze with `--annotation-status adjudicated`.

## Change rules

Any edit to `v2.jsonl` changes its hash, and the dataset test fails until the file is re-frozen:
`python -m evaluation.freeze_golden_dataset evaluation/golden_datasets/ticket_triage/v2.jsonl`.
Bump `dataset_version` in every line whenever labels change, and re-approve the regression-gate
baselines (their "same answer key" check fails until you do). Benchmark results record the hash,
and results from different hashes are never compared. Never edit `v1.jsonl`.
