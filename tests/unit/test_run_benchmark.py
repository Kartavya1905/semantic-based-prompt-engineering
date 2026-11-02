"""
FILE:         tests/unit/test_run_benchmark.py
WHAT IT DOES: Runs the real benchmark runner against an "oracle" fake model that knows every
              answer, to check the grid size, resuming, error handling, model ordering,
              traceability keys and the quick summary.
WHERE IT FITS: Phase 6. Offline; a whole benchmark runs in well under a second.
"""

import shutil

import pytest

from evaluation.experiment_config import ExperimentConfig
from evaluation.golden_case_model import compute_dataset_sha256, load_golden_cases
from evaluation.results_io import latest_records_per_run, load_result_records
from evaluation.run_benchmark import BenchmarkAbortedError, plan_runs, run_experiment
from evaluation.summarize_results import load_quality_frame, summarize_by_variant
from prompt_engine.registry import PromptRegistry
from prompt_engine.settings import PROJECT_ROOT, get_settings
from tests.fakes import OracleLLMClient

DATASET_PATH = PROJECT_ROOT / "evaluation" / "golden_datasets" / "ticket_triage" / "v2.jsonl"
SMOKE_CASE_COUNT = 11


# --- 1. Fixtures ---------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def answers_by_body() -> dict[str, dict]:
    """The perfect answer for every smoke ticket, keyed by ticket body."""
    return {
        case.input_variables["ticket_body"]: case.expected_output | {
            "summary": case.reference_summary, "confidence_score": 0.9,
        }
        for case in load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    }


def build_config(**overrides) -> ExperimentConfig:
    return ExperimentConfig.model_validate({
        "experiment_id": "unit_test_run",
        "description": "Oracle run used by unit tests.",
        "prompt_id": "ticket_triage",
        "prompt_versions": ["v1_baseline", "v3_fewshot"],
        "model_names": ["fake-model-a"],
        "temperatures": [0.0, 0.7],
        "seeds": [1, 2],
        "dataset_path": str(DATASET_PATH),
        "dataset_split": "dev",
        "required_tag": "smoke",
        "compute_summary_similarity": False,
    } | overrides)


def oracle_factory(answers_by_body, **oracle_options):
    created_clients: dict[str, OracleLLMClient] = {}

    def create_client(model_name: str) -> OracleLLMClient:
        created_clients[model_name] = OracleLLMClient(
            answers_by_body, model_name=model_name, **oracle_options
        )
        return created_clients[model_name]

    return create_client, created_clients


# --- 2. Grid expansion ---------------------------------------------------------------------------
def test_grid_size_and_greedy_seed_collapse():
    config = build_config()
    golden_cases = load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    runs = plan_runs(config, golden_cases, "f" * 64, PromptRegistry())["fake-model-a"]
    # 2 variants × (1 seed at T=0 + 2 seeds at T=0.7) × 11 cases
    assert len(runs) == 2 * (1 + 2) * SMOKE_CASE_COUNT
    assert len({run.run_key for run in runs}) == len(runs)
    greedy_seeds = {
        run.run_metadata["seed"] for run in runs if run.run_metadata["temperature"] == 0
    }
    assert greedy_seeds == {1}


def test_editing_a_prompt_changes_the_run_keys(tmp_path):
    edited_prompts_root = tmp_path / "prompts"
    shutil.copytree(get_settings().prompts_root, edited_prompts_root)
    persona_path = edited_prompts_root / "system" / "personas" / "support_triage_analyst.md"
    persona_path.write_text(persona_path.read_text(encoding="utf-8") + "\nBe kind.", "utf-8")

    config = build_config(prompt_versions=["v1_baseline"], temperatures=[0.0])
    golden_cases = load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    original_keys = {run.run_key for run in
                     plan_runs(config, golden_cases, "f" * 64, PromptRegistry())["fake-model-a"]}
    edited_keys = {run.run_key for run in plan_runs(
        config, golden_cases, "f" * 64, PromptRegistry(edited_prompts_root))["fake-model-a"]}
    assert original_keys.isdisjoint(edited_keys)


def test_editing_generation_settings_changes_the_run_keys(tmp_path):
    # Same prompt text (same fingerprint), but a shorter answer limit can change every answer.
    edited_prompts_root = tmp_path / "prompts"
    shutil.copytree(get_settings().prompts_root, edited_prompts_root)
    manifest_path = edited_prompts_root / "manifests" / "ticket_triage" / "v1_baseline.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "max_output_tokens: 512" in manifest_text
    manifest_path.write_text(
        manifest_text.replace("max_output_tokens: 512", "max_output_tokens: 256"), "utf-8"
    )

    config = build_config(prompt_versions=["v1_baseline"], temperatures=[0.0])
    golden_cases = load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    original_runs = plan_runs(config, golden_cases, "f" * 64, PromptRegistry())["fake-model-a"]
    edited_runs = plan_runs(
        config, golden_cases, "f" * 64, PromptRegistry(edited_prompts_root)
    )["fake-model-a"]
    assert original_runs[0].composed_prompt.prompt_fingerprint == (
        edited_runs[0].composed_prompt.prompt_fingerprint
    )
    assert {run.run_key for run in original_runs}.isdisjoint(run.run_key for run in edited_runs)


# --- 3. A full run, scored ---------------------------------------------------------------------
async def test_oracle_run_scores_perfectly(tmp_path, answers_by_body):
    create_client, _ = oracle_factory(answers_by_body)
    results_path = await run_experiment(build_config(), create_client, results_dir=tmp_path)

    records = load_result_records(results_path)
    assert len(records) == 2 * 3 * SMOKE_CASE_COUNT
    assert all(record["all_labels_correct"] and record["first_pass_valid"] for record in records)
    assert {record["dataset_sha256"] for record in records} == {
        compute_dataset_sha256(DATASET_PATH)[:12]
    }

    quality_frame, infrastructure_error_count = load_quality_frame(results_path)
    summary = summarize_by_variant(quality_frame)
    assert infrastructure_error_count == 0
    assert (summary["all_labels_acc"] == 1.0).all()
    assert (summary["escalation_recall"] == 1.0).all()


async def test_repairs_show_up_as_not_first_pass(tmp_path, answers_by_body):
    broken_body = next(iter(answers_by_body))
    create_client, _ = oracle_factory(answers_by_body, broken_first_reply_bodies={broken_body})
    config = build_config(prompt_versions=["v1_baseline"], temperatures=[0.0])
    records = load_result_records(await run_experiment(config, create_client, results_dir=tmp_path))

    repaired = [record for record in records if not record["first_pass_valid"]]
    assert len(repaired) == 1
    assert repaired[0]["schema_valid"] and repaired[0]["attempts_used"] == 2
    assert repaired[0]["first_attempt_error_types"] == ["json_invalid"]


# --- 4. Resuming ---------------------------------------------------------------------------------
async def test_rerun_skips_finished_runs(tmp_path, answers_by_body):
    config = build_config()
    first_factory, _ = oracle_factory(answers_by_body)
    await run_experiment(config, first_factory, results_dir=tmp_path)

    second_factory, second_clients = oracle_factory(answers_by_body)
    results_path = await run_experiment(config, second_factory, results_dir=tmp_path)
    assert second_clients == {}  # nothing pending, so no client was even created
    assert len(load_result_records(results_path)) == 2 * 3 * SMOKE_CASE_COUNT


async def test_server_down_aborts_then_resume_finishes(tmp_path, answers_by_body):
    config = build_config(prompt_versions=["v1_baseline"], temperatures=[0.0])
    failing_factory, _ = oracle_factory(answers_by_body, always_fail=True)
    with pytest.raises(BenchmarkAbortedError, match="5 infrastructure errors in a row"):
        await run_experiment(config, failing_factory, results_dir=tmp_path)

    working_factory, _ = oracle_factory(answers_by_body)
    results_path = await run_experiment(config, working_factory, results_dir=tmp_path)
    final_records = latest_records_per_run(load_result_records(results_path))
    assert len(final_records) == SMOKE_CASE_COUNT
    assert all(record["infrastructure_error"] is None for record in final_records)


# --- 5. One model at a time --------------------------------------------------------------------
async def test_models_run_one_after_another(tmp_path, answers_by_body):
    shared_events: list[tuple[str, str]] = []
    create_client, _ = oracle_factory(answers_by_body, events=shared_events)
    config = build_config(model_names=["fake-model-a", "fake-model-b"], temperatures=[0.0])
    await run_experiment(config, create_client, results_dir=tmp_path)

    model_sequence = [model_name for _, model_name in shared_events]
    first_b_index = model_sequence.index("fake-model-b")
    assert set(model_sequence[:first_b_index]) == {"fake-model-a"}
    assert shared_events[first_b_index - 1] == ("close", "fake-model-a")


async def test_a_run_killed_mid_write_resumes_cleanly(tmp_path, answers_by_body):
    config = build_config(prompt_versions=["v1_baseline"], temperatures=[0.0])
    first_factory, _ = oracle_factory(answers_by_body)
    results_path = await run_experiment(config, first_factory, results_dir=tmp_path)

    # Simulate a crash during the last write: the final row is cut off halfway.
    complete_text = results_path.read_text(encoding="utf-8")
    last_row_start = complete_text.rstrip("\n").rfind("\n") + 1
    results_path.write_text(complete_text[: last_row_start + 40], encoding="utf-8")
    assert len(load_result_records(results_path)) == SMOKE_CASE_COUNT - 1  # half row skipped

    second_factory, _ = oracle_factory(answers_by_body)
    await run_experiment(config, second_factory, results_dir=tmp_path)
    final_records = load_result_records(results_path)
    assert len(final_records) == SMOKE_CASE_COUNT  # only the cut-off run was redone
    assert len({record["run_key"] for record in final_records}) == SMOKE_CASE_COUNT


def test_a_broken_line_in_the_middle_is_an_error(tmp_path):
    results_path = tmp_path / "damaged.jsonl"
    results_path.write_text('{"run_key": "a"}\n{"run_k\n{"run_key": "c"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="damaged.jsonl:2 is not valid JSON"):
        load_result_records(results_path)


def test_empty_filter_is_an_error(tmp_path):
    import asyncio

    config = build_config(required_tag="smoke", dataset_split="test")  # smoke is dev-only
    with pytest.raises(ValueError, match="selected no cases"):
        asyncio.run(run_experiment(config, lambda name: OracleLLMClient({}), results_dir=tmp_path))


# --- 6. Summary guard: a prompt edited without a version bump is flagged -------------------------
def test_mixed_fingerprints_within_one_version_are_flagged():
    import pandas as pd

    from evaluation.summarize_results import versions_with_several_fingerprints

    quality_frame = pd.DataFrame({
        "prompt_version": ["v1_baseline", "v1_baseline", "v3_fewshot"],
        "manifest_version": ["1.0.0", "1.0.0", "1.0.0"],
        "prompt_fingerprint": ["aaa", "bbb", "ccc"],
    })
    assert versions_with_several_fingerprints(quality_frame) == ["v1_baseline 1.0.0"]
