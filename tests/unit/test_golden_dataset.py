"""
FILE:         tests/unit/test_golden_dataset.py
WHAT IT DOES: Quality gate for the answer key: valid labels, policy-consistent escalation,
              entities really in the text, no leakage from few-shot examples, no duplicates,
              full coverage in both splits, and an unchanged frozen hash.
WHERE IT FITS: Phase 5. A wrong answer key silently ruins every benchmark, so it is tested
              as strictly as code.
"""

import json
from difflib import SequenceMatcher
from itertools import combinations

import pytest
import yaml

from evaluation.golden_case_model import (
    GoldenCase,
    GoldenDatasetError,
    compute_dataset_sha256,
    load_golden_cases,
    validate_labels_against_contract,
)
from prompt_engine.registry import PromptRegistry
from prompt_engine.schemas.ticket_triage import TicketCategory, TicketTriageResult, UrgencyLevel
from prompt_engine.settings import PROJECT_ROOT

DATASET_DIR = PROJECT_ROOT / "evaluation" / "golden_datasets" / "ticket_triage"
DATASET_PATH = DATASET_DIR / "v2.jsonl"
MANIFEST_PATH = DATASET_DIR / "v2.manifest.json"
KEY_SLICES = {"prompt_injection", "non_english", "security", "legal_or_deletion",
              "missing_info", "multi_issue", "very_long", "rule_order", "ambiguous"}


# --- 1. Fixtures ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def golden_cases() -> list[GoldenCase]:
    return load_golden_cases(DATASET_PATH)


def ticket_text(case: GoldenCase) -> str:
    return f"{case.input_variables['ticket_subject']}\n{case.input_variables['ticket_body']}"


def text_similarity(first_text: str, second_text: str) -> float:
    return SequenceMatcher(None, first_text.lower(), second_text.lower()).ratio()


# --- 2. Every label is a valid answer under the output contract -----------------------------
def test_every_case_has_contract_valid_labels(golden_cases):
    for case in golden_cases:
        validate_labels_against_contract(case, TicketTriageResult)  # raises if invalid


def test_inputs_match_the_template_variables(golden_cases):
    manifest = PromptRegistry().load_manifest("ticket_triage", "v1_baseline")
    required_variables = set(manifest.human_template.required_variables)
    for case in golden_cases:
        assert set(case.input_variables) == required_variables, case.case_id
        assert case.input_variables["customer_tier"] in {"free", "pro", "enterprise"}


def test_escalation_labels_follow_the_policy(golden_cases):
    """Rules 5-8: escalate iff critical, enterprise+high, or a legal/deletion ticket."""
    for case in golden_cases:
        labels = case.expected_output
        is_enterprise = case.input_variables["customer_tier"] == "enterprise"
        should_escalate = (
            labels["urgency"] == "critical"
            or (labels["urgency"] == "high" and is_enterprise)
            or "legal_or_deletion" in case.slice_tags
        )
        assert labels["requires_human_escalation"] is should_escalate, case.case_id


def test_entities_appear_literally_in_the_ticket(golden_cases):
    for case in golden_cases:
        for entity in case.expected_output["extracted_entities"]:
            assert entity["entity_value"] in ticket_text(case), (case.case_id, entity)


def test_hard_and_ambiguous_cases_explain_their_labels(golden_cases):
    for case in golden_cases:
        if case.difficulty == "hard" or "ambiguous" in case.slice_tags:
            assert case.label_rationale, f"{case.case_id} needs a label_rationale"


# --- 3. No leakage and no duplicates ----------------------------------------------------------
def test_no_case_copies_a_few_shot_example(golden_cases):
    fragments_dir = PROJECT_ROOT / "prompts" / "fragments" / "ticket_triage"
    few_shot_bodies = [
        example["input_variables"]["ticket_body"]
        for examples_path in sorted(fragments_dir.glob("*.yaml"))
        for example in yaml.safe_load(examples_path.read_text(encoding="utf-8"))
    ]
    for case, few_shot_body in [(c, b) for c in golden_cases for b in few_shot_bodies]:
        similarity = text_similarity(case.input_variables["ticket_body"], few_shot_body)
        assert similarity < 0.6, f"{case.case_id} resembles a few-shot example ({similarity:.2f})"


def test_no_near_duplicate_tickets(golden_cases):
    for first_case, second_case in combinations(golden_cases, 2):
        similarity = text_similarity(ticket_text(first_case), ticket_text(second_case))
        assert similarity < 0.8, f"{first_case.case_id} ~ {second_case.case_id} ({similarity:.2f})"


# --- 4. Coverage: both splits can measure every class and every key slice --------------------
@pytest.mark.parametrize("split", ["dev", "test"])
def test_each_split_covers_every_category_urgency_and_slice(golden_cases, split):
    split_cases = [case for case in golden_cases if case.split == split]
    assert {case.expected_output["category"] for case in split_cases} == set(TicketCategory)
    assert {case.expected_output["urgency"] for case in split_cases} == set(UrgencyLevel)
    assert KEY_SLICES <= {tag for case in split_cases for tag in case.slice_tags}


def test_held_out_split_is_30_to_50_percent(golden_cases):
    test_fraction = sum(case.split == "test" for case in golden_cases) / len(golden_cases)
    assert 0.3 <= test_fraction <= 0.5


def test_smoke_subset_is_small_but_covers_every_urgency(golden_cases):
    smoke_cases = load_golden_cases(DATASET_PATH, split="dev", required_tag="smoke")
    assert 8 <= len(smoke_cases) <= 15
    assert {case.expected_output["urgency"] for case in smoke_cases} == set(UrgencyLevel)


# --- 5. Frozen: the file matches its manifest ---------------------------------------------------
def test_dataset_matches_its_frozen_manifest(golden_cases):
    """Edited the dataset? Bump dataset_version, then: python -m evaluation.freeze_golden_dataset"""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert compute_dataset_sha256(DATASET_PATH) == manifest["sha256"]
    assert manifest["case_count"] == len(golden_cases)
    assert manifest["dataset_version"] == golden_cases[0].dataset_version


# --- 6. The loader rejects malformed datasets ---------------------------------------------------
def write_dataset(tmp_path, records):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    return dataset_path


@pytest.fixture
def valid_record() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8").splitlines()[0])


def test_unknown_tag_is_rejected_with_line_number(tmp_path, valid_record):
    dataset_path = write_dataset(tmp_path, [valid_record | {"slice_tags": ["smok"]}])
    with pytest.raises(GoldenDatasetError, match="(?s)dataset.jsonl:1.*unknown slice_tags"):
        load_golden_cases(dataset_path)


def test_smoke_case_in_test_split_is_rejected(tmp_path, valid_record):
    dataset_path = write_dataset(tmp_path, [valid_record | {"split": "test"}])
    with pytest.raises(GoldenDatasetError, match="smoke cases must be in the dev split"):
        load_golden_cases(dataset_path)


def test_duplicate_case_id_is_rejected(tmp_path, valid_record):
    with pytest.raises(GoldenDatasetError, match="duplicate case_id"):
        load_golden_cases(write_dataset(tmp_path, [valid_record, valid_record]))


def test_mixed_versions_are_rejected(tmp_path, valid_record):
    second_record = valid_record | {"case_id": "TT-9999", "dataset_version": "9.9.9"}
    with pytest.raises(GoldenDatasetError, match="mixed dataset_version"):
        load_golden_cases(write_dataset(tmp_path, [valid_record, second_record]))


def test_split_and_tag_filters(golden_cases):
    dev_cases = load_golden_cases(DATASET_PATH, split="dev")
    assert {case.split for case in dev_cases} == {"dev"}
    injection_cases = load_golden_cases(DATASET_PATH, required_tag="prompt_injection")
    assert all("prompt_injection" in case.slice_tags for case in injection_cases)
