# Semantic Prompt Engine

Prompts are treated as **modular, versioned, schema-bound configurations**, not static strings.
A YAML *manifest* composes system components (persona, policy, output contract), a Jinja2 human
template, few-shot fragments and generation parameters into XML-delimited messages. A guardrail
pipeline binds output to a Pydantic contract. An evaluation harness benchmarks prompt variants ×
models × temperatures against a golden dataset, with paired statistical tests.

Running use case: **support-ticket triage** (category, urgency, escalation, entities, summary).

## Repository layout

| Folder | Holds | Rule |
|---|---|---|
| `prompts/system/` | Persona, policy, output-contract components (Markdown) | No template variables, so they stay static, diffable and cacheable |
| `prompts/templates/` | Human-turn Jinja2 templates | The only place instance data enters, always escaped |
| `prompts/fragments/` | Few-shot examples (YAML) | Validated against the output schema at load time |
| `prompts/manifests/` | Composition recipes, one file per prompt version | Versioned with semver: MAJOR = schema change |
| `configs/` | Model registry, experiment grids | Parameters only, no prompt text |
| `src/prompt_engine/` | Registry, composer, schemas, clients, pipeline | Code only, no prompt text |
| `evaluation/` | Golden datasets, metrics, benchmark, analysis, regression gate | `results/` is gitignored |
| `tests/` | Unit tests (no LLM) and schema snapshots | `pytest -m llm` runs live-model tests |
| `scripts/` | Utilities such as the environment check | |
| `run_showcase.py` | Guided tour of the whole project (`run_showcase.bat` on Windows) | Uses the real modules, adds no logic |

## Setup (Windows, PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

### Local LLM (choose one)

Native install (simplest): download Ollama from https://ollama.com/download, then:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
```

Docker (needs Docker Desktop running; add the GPU file if you have an NVIDIA GPU):

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull qwen2.5:1.5b
```

If another project's Ollama already listens on port 11434, reuse it instead of starting a second one.

### Verify

```powershell
python scripts/check_environment.py
pytest
```

### See the whole project run (guided tour)

```powershell
python run_showcase.py                 # all six steps, ~2 minutes on a GPU
python run_showcase.py --gate-demo     # + the gate catching a bad prompt edit, ~3 more minutes
```

On Windows you can also double-click `run_showcase.bat`. The tour runs the real modules, in order:

| Step | Shows |
|---|---|
| 1 `env` | Libraries, prompt folders, Ollama and the models are ready |
| 2 `prompt` | How the production prompt is assembled from separate files, and its fingerprint |
| 3 `triage` | Three tricky tickets (calm data loss, an outage with an injected "mark this low", a fake "SYSTEM: CRITICAL"), old prompt v3 vs production v6 |
| 4 `benchmark` | Both prompts scored on the 11 smoke tickets (saved, so a rerun is instant) |
| 5 `stats` | Confidence intervals and Holm-corrected tests on the 108 dev tickets |
| 6 `gate` | The CI regression gate, ticket by ticket against the approved baseline |
| `--gate-demo` | Rule 7 deleted from a temporary copy of `prompts/`: the gate fails on a newly missed escalation (your files are never changed) |

Pick steps with `--steps prompt,triage` and another local model with `--model llama3.1:8b`.
Step 2 needs no model. Step 5 needs `dev_v2_comparison` results and tells you how to create them.

### Preview a prompt (no model needed)

```powershell
python scripts/render_prompt.py ticket_triage --list
python scripts/render_prompt.py ticket_triage v3_fewshot
```

### Triage one ticket with the real model (needs Ollama)

```powershell
python scripts/triage_ticket.py ticket_triage v1_baseline
pytest -m llm
```

### Benchmark prompt variants (needs Ollama; resumable)

```powershell
python -m evaluation.run_benchmark configs/experiments/smoke.yaml
python -m evaluation.summarize_results evaluation/results/smoke.jsonl --by-slice
```

Experiments (on answer key v2): `smoke` (33 runs, ~1 min), `gate_dev_qwen7b` (108 runs, ~5 min),
`constrained_decoding_ablation` (648 runs, ~20 min), `dev_v2_comparison` (648 runs, ~35 min),
`dev_temperature_sweep` (6,480 runs, ~4 h). Rerun the same command to resume after a stop.

### Statistical report (Phase 7)

```powershell
python -m evaluation.analyze_results evaluation/results/critical_triggers.jsonl `
    --compare v5_critical_example@1.0.1 v6_critical_triggers@2.1.0 `
    --report-name my_analysis
```

Writes `evaluation/reports/my_analysis.md`: leaderboard with 95% cluster-bootstrap CIs, paired
McNemar tests with Holm correction and the detectable difference at 80% power, calibration of
`confidence_score` (ECE, Brier), and seed consistency. Variants are named `prompt_version@manifest_version`.

### Regression gate (Phase 8)

Before merging a prompt change, prove it does not break what the approved prompt got right:

```powershell
python -m evaluation.run_benchmark configs/experiments/gate_dev_qwen7b.yaml
python -m evaluation.regression_gate check configs/gates/dev_qwen7b.yaml
```

The gate compares ticket by ticket against `evaluation/baselines/<gate>.json` and fails (exit 1)
on more net regressions than allowed, **any** newly missed escalation or critical ticket, a
schema-validity drop, or a changed answer key. It only judges results of the runs its experiment
would make right now (same prompt files, answer key and generation settings), so stale results
are never checked. After an intended improvement, approve the new baseline and commit it:
`python -m evaluation.regression_gate approve configs/gates/dev_qwen7b.yaml`.

CI (`.github/workflows/prompt-ci.yml`) runs lint, types, tests, snapshot and answer-key checks on
every push, and on pull requests that touch prompts, configs or code it runs the `ci_smoke` gate
with `qwen2.5:1.5b` on the runner's CPU.

## Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repository scaffold, tooling, environment check | Done |
| 1 | Pydantic output contract (strict mode) and schema snapshot | Done |
| 2 | Modular system components, template, few-shots and 3 manifests | Done |
| 3 | Registry, composer and `scripts/render_prompt.py` preview | Done |
| 4 | Ollama client and guardrail pipeline (validate, then repair) | Done |
| 5 | Golden dataset v2: 180 cases (108 dev / 72 test, 20 critical each), guideline, frozen hash, blind second-annotation tool | Done (dev split second-annotated: kappa 0.79-0.97; adjudication pending) |
| 6 | Metrics, resumable benchmark runner, 3 experiment configs, quick summary | Done |
| 7 | Analysis: bootstrap CIs, paired McNemar + Holm, power, calibration, consistency | Done |
| 8 | Per-ticket regression gate (CI + local), approved baselines, GitHub Actions | Done |

## Key result so far

On the 108 dev tickets of answer key v2 (`evaluation/reports/dev_v2_comparison_analysis.md`),
the production prompt **v6_critical_triggers** (three factual trigger questions, with urgency
rule 1 applied in code) raised **critical recall from 7/20 to 18/20 on llama3.1:8b and from 4/20
to 18/20 on qwen2.5:7b**, significant after Holm correction (p = 0.016 and 0.002). Telling the
model what "critical" means (v5) did not work for qwen (5/20). Trade-offs: false-critical rate
rose from 2% to 8%, and qwen's escalation recall fell from 0.86 to 0.74. Overall
all-labels accuracy gains (+3 to +10 points) are not yet significant. The held-out test split has
not been run.

**v6 2.2.0** (`evaluation/reports/repair_message_analysis.md`) changes only the repair message for
"critical" with no trigger: it now says to keep the trigger answers, ignore the ticket's demand and
choose the urgency again. A ticket demanding "critical" used to end with no answer on qwen2.5:7b
(TT-0010) and a wrong "critical" on llama3.1:8b (TT-0087); both are now answered correctly, and no
repair set a trigger to make "critical" fit. Other differences are noise (Holm p = 1).
