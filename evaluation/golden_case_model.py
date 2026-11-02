"""
FILE:         evaluation/golden_case_model.py
WHAT IT DOES: The shape of one golden-dataset case (a ticket plus its agreed correct answer),
              a strict JSONL loader, and helpers to check labels against the output contract and
              fingerprint the dataset file.
WHERE IT FITS: Phase 5. The benchmark (Phase 6) loads cases through load_golden_cases().
USED BY:      run_benchmark.py, annotation_agreement.py, freeze_golden_dataset.py, tests
"""

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from prompt_engine.schemas import validate_as_model_output

# --- 1. Controlled tag vocabulary (see ANNOTATION_GUIDELINE.md §4): a typo is an error ---------
ALLOWED_SLICE_TAGS = frozenset({
    "smoke", "ambiguous", "policy_gap", "multi_issue", "prompt_injection", "non_english",
    "very_long", "missing_info", "security", "legal_or_deletion", "rule_order",
})


class GoldenDatasetError(Exception):
    """The dataset file is malformed: bad line, duplicate case_id, mixed versions."""


# --- 2. One case ---------------------------------------------------------------------------------
class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str = Field(pattern=r"^[A-Z]{2}-\d{4}$")
    split: Literal["dev", "test"]
    difficulty: Literal["easy", "medium", "hard"]
    slice_tags: list[str]
    input_variables: dict[str, str]
    # The labelled fields of the answer. summary and confidence_score are NOT labelled:
    # the summary is compared to reference_summary by meaning, and confidence has no single truth.
    expected_output: dict[str, Any]
    reference_summary: str
    label_rationale: str | None = None
    annotator_ids: list[str] = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")

    @model_validator(mode="after")
    def tags_are_known_and_smoke_is_dev_only(self) -> "GoldenCase":
        unknown_tags = set(self.slice_tags) - ALLOWED_SLICE_TAGS
        if unknown_tags:
            raise ValueError(f"unknown slice_tags {sorted(unknown_tags)}")
        if len(set(self.slice_tags)) != len(self.slice_tags):
            raise ValueError("duplicate slice_tags")
        if "smoke" in self.slice_tags and self.split != "dev":
            raise ValueError("smoke cases must be in the dev split (CI must never see test)")
        return self


# --- 3. Strict loader: every line validated, ids unique, one dataset version ------------------
def load_golden_cases(
    dataset_path: Path, split: str | None = None, required_tag: str | None = None
) -> list[GoldenCase]:
    all_cases: list[GoldenCase] = []
    with dataset_path.open(encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                all_cases.append(GoldenCase.model_validate_json(line))
            except ValidationError as validation_error:
                raise GoldenDatasetError(
                    f"{dataset_path.name}:{line_number}: {validation_error}"
                ) from validation_error

    case_ids = [case.case_id for case in all_cases]
    if len(set(case_ids)) != len(case_ids):
        raise GoldenDatasetError(f"duplicate case_id in {dataset_path.name}")
    if len({case.dataset_version for case in all_cases}) > 1:
        raise GoldenDatasetError(f"mixed dataset_version values in {dataset_path.name}")

    return [
        case for case in all_cases
        if (split is None or case.split == split)
        and (required_tag is None or required_tag in case.slice_tags)
    ]


# --- 4. Labels must obey the SAME contract as model answers (types, enums, business rules) ----
def validate_labels_against_contract(case: GoldenCase, contract: type[BaseModel]) -> BaseModel:
    candidate_answer = case.expected_output | {
        "summary": case.reference_summary,
        "confidence_score": 1.0,
    }
    return validate_as_model_output(contract, candidate_answer)


# --- 5. Fingerprint of the file: any edit changes it, so results always name their dataset ----
def compute_dataset_sha256(dataset_path: Path) -> str:
    return hashlib.sha256(dataset_path.read_bytes()).hexdigest()
