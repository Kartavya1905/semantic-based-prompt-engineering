"""
FILE:         evaluation/experiment_config.py
WHAT IT DOES: Validates an experiment YAML (configs/experiments/*.yaml): the grid of prompt
              variants × models × temperatures × seeds × decoding modes to run on a dataset split.
WHERE IT FITS: Phase 6. run_benchmark.py expands this grid into individual runs.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from prompt_engine.settings import PROJECT_ROOT


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # --- 1. What to run ---
    experiment_id: str = Field(pattern=r"^[a-z0-9_]+$", description="also the results file name")
    description: str
    prompt_id: str
    prompt_versions: list[str] = Field(min_length=1)
    model_names: list[str] = Field(min_length=1)
    temperatures: list[float] = Field(min_length=1)
    seeds: list[int] = Field(min_length=1)
    constrained_decoding_modes: list[bool] = Field(default=[True], min_length=1)

    # --- 2. On which cases ---
    dataset_path: Path
    dataset_split: Literal["dev", "test"]
    required_tag: str | None = None

    # --- 3. How ---
    max_repair_attempts: int = Field(default=2, ge=0)
    max_concurrency: int = Field(default=2, ge=1, description="requests in flight per model")
    compute_summary_similarity: bool = True

    @field_validator("temperatures")
    @classmethod
    def temperatures_in_range(cls, temperatures: list[float]) -> list[float]:
        if any(not 0.0 <= temperature <= 2.0 for temperature in temperatures):
            raise ValueError("temperatures must be within 0.0-2.0")
        return temperatures

    @property
    def resolved_dataset_path(self) -> Path:
        if self.dataset_path.is_absolute():
            return self.dataset_path
        return PROJECT_ROOT / self.dataset_path

    def seeds_for(self, temperature: float) -> list[int]:
        """At temperature 0 decoding is greedy, so extra seeds only repeat the same run."""
        return self.seeds[:1] if temperature == 0.0 else self.seeds


def load_experiment_config(config_path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))
