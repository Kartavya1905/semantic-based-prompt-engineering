"""
FILE:         evaluation/run_benchmark.py
WHAT IT DOES: Runs an experiment grid (prompt variants × models × temperatures × seeds ×
              decoding modes) over golden cases, scores every answer, and appends one JSONL row
              per run to evaluation/results/<experiment_id>.jsonl.
WHERE IT FITS: Phase 6. The engine that turns "which prompt is better?" into data.
PROPERTIES:   - Resumable: rerun the same command after a crash; finished runs are skipped.
              - Traceable: every row records the prompt fingerprint and dataset hash.
              - Model by model: one model is finished before the next loads (8 GB of VRAM
                cannot hold two 7B models, and swapping costs seconds per switch).
              - Fails fast: stops if Ollama keeps failing, instead of logging 2,000 errors.
USE:          python -m evaluation.run_benchmark configs/experiments/smoke.yaml
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.experiment_config import ExperimentConfig, load_experiment_config
from evaluation.golden_case_model import GoldenCase, compute_dataset_sha256, load_golden_cases
from evaluation.metrics import SummarySimilarityScorer, score_case
from evaluation.results_io import completed_run_keys
from prompt_engine.clients.base import LLMClient, LLMTransportError
from prompt_engine.clients.ollama_client import OllamaClient
from prompt_engine.composer import ComposedPrompt, PromptComposer
from prompt_engine.pipeline import StructuredPromptPipeline
from prompt_engine.registry import PromptRegistry
from prompt_engine.settings import get_settings

ClientFactory = Callable[[str], LLMClient]
MAX_CONSECUTIVE_INFRASTRUCTURE_ERRORS = 5
PROGRESS_EVERY_N_RUNS = 25


class BenchmarkAbortedError(Exception):
    """Too many infrastructure errors in a row: the server is down, not the prompt."""


# --- 1. One planned run = one (variant, model, temperature, seed, mode, case) cell of the grid --
@dataclass(frozen=True)
class PlannedRun:
    run_key: str
    run_metadata: dict[str, Any]
    composed_prompt: ComposedPrompt
    golden_case: GoldenCase
    use_constrained_decoding: bool


# The key names everything that can change an answer. Editing a prompt changes its fingerprint,
# editing the dataset changes its hash: both produce NEW keys, so stale rows are never reused.
RUN_KEY_FIELDS = (
    "prompt_version", "prompt_fingerprint", "dataset_sha256", "model_name", "temperature",
    "seed", "constrained_decoding", "max_repair_attempts",
)


def build_run_key(run_metadata: dict[str, Any], case_id: str) -> str:
    return "|".join(str(run_metadata[field_name]) for field_name in RUN_KEY_FIELDS) + f"|{case_id}"


# --- 2. Expand the config into runs, grouped by model --------------------------------------------
def plan_runs(
    config: ExperimentConfig,
    golden_cases: list[GoldenCase],
    dataset_sha256: str,
    registry: PromptRegistry,
) -> dict[str, list[PlannedRun]]:
    composer = PromptComposer(registry)
    runs_by_model: dict[str, list[PlannedRun]] = {name: [] for name in config.model_names}

    for model_name in config.model_names:
        for prompt_version in config.prompt_versions:
            manifest = registry.load_manifest(config.prompt_id, prompt_version)
            for temperature in config.temperatures:
                for seed in config.seeds_for(temperature):
                    for use_constrained_decoding in config.constrained_decoding_modes:
                        for golden_case in golden_cases:
                            composed_prompt = composer.compose(
                                manifest, golden_case.input_variables,
                                generation_overrides={"temperature": temperature, "seed": seed},
                            )
                            run_metadata = {
                                "experiment_id": config.experiment_id,
                                "prompt_id": config.prompt_id,
                                "prompt_version": prompt_version,
                                "manifest_version": manifest.version,
                                "prompt_fingerprint": composed_prompt.prompt_fingerprint,
                                "dataset_version": golden_case.dataset_version,
                                "dataset_sha256": dataset_sha256[:12],
                                "model_name": model_name,
                                "temperature": temperature,
                                "seed": seed,
                                "constrained_decoding": use_constrained_decoding,
                                "max_repair_attempts": config.max_repair_attempts,
                            }
                            runs_by_model[model_name].append(PlannedRun(
                                run_key=build_run_key(run_metadata, golden_case.case_id),
                                run_metadata=run_metadata,
                                composed_prompt=composed_prompt,
                                golden_case=golden_case,
                                use_constrained_decoding=use_constrained_decoding,
                            ))
    return runs_by_model


# --- 3. Execute one run and turn it into a result row --------------------------------------------
async def execute_run(
    planned_run: PlannedRun,
    pipeline: StructuredPromptPipeline,
    semaphore: asyncio.Semaphore,
    similarity_scorer: SummarySimilarityScorer | None,
) -> dict[str, Any]:
    golden_case = planned_run.golden_case
    base_row = planned_run.run_metadata | {
        "run_key": planned_run.run_key,
        "case_id": golden_case.case_id,
        "split": golden_case.split,
        "difficulty": golden_case.difficulty,
        "slice_tags": golden_case.slice_tags,
    }
    async with semaphore:
        try:
            outcome = await pipeline.run(planned_run.composed_prompt)
        except LLMTransportError as transport_error:
            # Recorded, but excluded from quality metrics and retried on the next resume.
            return base_row | {"infrastructure_error": str(transport_error),
                               "completed_at": utc_timestamp()}

    scored_row = score_case(golden_case, outcome)
    summary_similarity = (
        similarity_scorer.similarity(scored_row["predicted_summary"], golden_case.reference_summary)
        if similarity_scorer is not None and scored_row["predicted_summary"] is not None
        else None
    )
    return base_row | {"infrastructure_error": None, "completed_at": utc_timestamp()} | (
        scored_row | {"summary_similarity": summary_similarity}
    )


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- 4. Run the whole experiment -----------------------------------------------------------------
async def run_experiment(
    config: ExperimentConfig,
    client_factory: ClientFactory = OllamaClient,
    results_dir: Path | None = None,
    similarity_scorer: SummarySimilarityScorer | None = None,
    registry: PromptRegistry | None = None,
) -> Path:
    golden_cases = load_golden_cases(
        config.resolved_dataset_path, split=config.dataset_split, required_tag=config.required_tag
    )
    if not golden_cases:
        raise ValueError("the dataset filter selected no cases")
    dataset_sha256 = compute_dataset_sha256(config.resolved_dataset_path)
    runs_by_model = plan_runs(config, golden_cases, dataset_sha256, registry or PromptRegistry())

    results_dir = results_dir or get_settings().results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / f"{config.experiment_id}.jsonl"
    already_done = completed_run_keys(results_path)
    total_runs = sum(len(runs) for runs in runs_by_model.values())
    print(f"{config.experiment_id}: {total_runs} runs planned, "
          f"{len(already_done & {r.run_key for runs in runs_by_model.values() for r in runs})} "
          f"already done", flush=True)

    for model_name, planned_runs in runs_by_model.items():
        pending_runs = [run for run in planned_runs if run.run_key not in already_done]
        if not pending_runs:
            continue

        # 4a. One client and one pipeline per decoding mode, for this model only.
        llm_client = client_factory(model_name)
        pipelines = {
            mode: StructuredPromptPipeline(
                llm_client, config.max_repair_attempts, use_constrained_decoding=mode
            )
            for mode in config.constrained_decoding_modes
        }
        semaphore = asyncio.Semaphore(config.max_concurrency)
        run_tasks = [
            asyncio.create_task(execute_run(
                run, pipelines[run.use_constrained_decoding], semaphore, similarity_scorer
            ))
            for run in pending_runs
        ]

        # 4b. Append each row the moment it finishes, so a crash loses at most in-flight runs.
        consecutive_errors = finished_count = 0
        try:
            with results_path.open("a", encoding="utf-8") as results_file:
                for finished_task in asyncio.as_completed(run_tasks):
                    result_row = await finished_task
                    results_file.write(json.dumps(result_row, ensure_ascii=False) + "\n")
                    results_file.flush()
                    finished_count += 1

                    if result_row["infrastructure_error"] is None:
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_INFRASTRUCTURE_ERRORS:
                            raise BenchmarkAbortedError(
                                f"{consecutive_errors} infrastructure errors in a row on "
                                f"{model_name}: {result_row['infrastructure_error']}"
                            )
                    if finished_count % PROGRESS_EVERY_N_RUNS == 0 or (
                        finished_count == len(pending_runs)
                    ):
                        print(f"  {model_name}: {finished_count}/{len(pending_runs)}", flush=True)
        finally:
            for run_task in run_tasks:
                run_task.cancel()
            await asyncio.gather(*run_tasks, return_exceptions=True)
            await llm_client.aclose()

    return results_path


# --- 5. CLI --------------------------------------------------------------------------------------
def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("config_path", type=Path)
    parsed_args = argument_parser.parse_args()
    config = load_experiment_config(parsed_args.config_path)

    similarity_scorer = (
        SummarySimilarityScorer(get_settings().embedding_model_name)
        if config.compute_summary_similarity else None
    )
    try:
        results_path = asyncio.run(run_experiment(config, similarity_scorer=similarity_scorer))
    except BenchmarkAbortedError as aborted_error:
        print(f"ABORTED: {aborted_error}\nFix the server, then rerun the same command to resume.")
        return 2
    print(f"\nResults: {results_path}\n"
          f"Summary: python -m evaluation.summarize_results {results_path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
