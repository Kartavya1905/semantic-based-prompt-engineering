"""
FILE:         tests/unit/test_annotation_agreement.py
WHAT IT DOES: Checks the second-annotator workflow: the exported sheet is blind, agreement and
              kappa are computed correctly, and incomplete sheets are refused.
WHERE IT FITS: Phase 5.
"""

import csv

import pytest

from evaluation.annotation_agreement import (
    LABELLED_FIELDS,
    compare_annotations,
    export_blind_sheet,
    normalise_label,
    read_sheet_labels,
)
from evaluation.golden_case_model import load_golden_cases
from prompt_engine.settings import PROJECT_ROOT

DATASET_PATH = PROJECT_ROOT / "evaluation" / "golden_datasets" / "ticket_triage" / "v2.jsonl"


@pytest.fixture(scope="module")
def dev_cases():
    return load_golden_cases(DATASET_PATH, split="dev")


def golden_labels_as_sheet(cases) -> dict[str, dict[str, str]]:
    """A second annotator who agrees with everything."""
    return {
        case.case_id: {name: str(case.expected_output[name]).lower() for name in LABELLED_FIELDS}
        for case in cases
    }


# --- 1. Export is blind -------------------------------------------------------------------------
def test_exported_sheet_has_tickets_but_no_labels(tmp_path, dev_cases):
    sheet_path = tmp_path / "sheet.csv"
    export_blind_sheet(dev_cases, sheet_path)
    with sheet_path.open(encoding="utf-8-sig", newline="") as sheet_file:
        rows = list(csv.DictReader(sheet_file))
    assert [row["case_id"] for row in rows] == [case.case_id for case in dev_cases]
    assert rows[0]["ticket_body"] == dev_cases[0].input_variables["ticket_body"]
    assert all(row[field_name] == "" for row in rows for field_name in LABELLED_FIELDS)


def test_sheet_round_trip_normalises_spreadsheet_values(tmp_path, dev_cases):
    sheet_path = tmp_path / "sheet.csv"
    export_blind_sheet(dev_cases[:1], sheet_path)
    blank_sheet_text = sheet_path.read_text(encoding="utf-8-sig")
    filled_text = blank_sheet_text.replace(",,,", ", Billing ,High,Yes", 1)
    sheet_path.write_text(filled_text, encoding="utf-8-sig")
    assert read_sheet_labels(sheet_path)[dev_cases[0].case_id] == {
        "category": "billing", "urgency": "high", "requires_human_escalation": "true",
    }


@pytest.mark.parametrize(("raw_label", "expected"), [
    ("Yes", "true"), ("FALSE", "false"), ("0", "false"), ("  Critical ", "critical"),
])
def test_normalise_label(raw_label, expected):
    assert normalise_label(raw_label) == expected


# --- 2. Agreement and kappa -------------------------------------------------------------------
def test_perfect_agreement_gives_kappa_one(dev_cases):
    field_agreements, disagreements = compare_annotations(
        dev_cases, golden_labels_as_sheet(dev_cases)
    )
    assert disagreements == []
    for agreement in field_agreements:
        assert agreement.percent_agreement == 1.0
        assert agreement.cohen_kappa == pytest.approx(1.0)


def test_disagreements_are_listed_and_lower_kappa(dev_cases):
    second_labels = golden_labels_as_sheet(dev_cases)
    second_labels["TT-0012"]["urgency"] = "high"  # the known ambiguous case
    field_agreements, disagreements = compare_annotations(dev_cases, second_labels)

    assert [(d.case_id, d.field_name, d.golden_label, d.second_label) for d in disagreements] == [
        ("TT-0012", "urgency", "critical", "high"),
    ]
    urgency_agreement = next(a for a in field_agreements if a.field_name == "urgency")
    assert urgency_agreement.percent_agreement == pytest.approx(107 / 108)
    assert urgency_agreement.cohen_kappa is not None and urgency_agreement.cohen_kappa < 1.0


def test_kappa_is_undefined_when_everyone_uses_one_label(dev_cases):
    one_class_cases = [case for case in dev_cases if case.expected_output["urgency"] == "low"]
    field_agreements, _ = compare_annotations(
        one_class_cases, golden_labels_as_sheet(one_class_cases)
    )
    urgency_agreement = next(a for a in field_agreements if a.field_name == "urgency")
    assert urgency_agreement.cohen_kappa is None


# --- 3. Incomplete sheets are refused ---------------------------------------------------------
def test_missing_case_is_refused(dev_cases):
    second_labels = golden_labels_as_sheet(dev_cases)
    del second_labels["TT-0001"]
    with pytest.raises(ValueError, match="no labels for \\['TT-0001'\\]"):
        compare_annotations(dev_cases, second_labels)


def test_empty_cell_is_refused(dev_cases):
    second_labels = golden_labels_as_sheet(dev_cases)
    second_labels["TT-0002"]["category"] = ""
    with pytest.raises(ValueError, match="empty label cells"):
        compare_annotations(dev_cases, second_labels)
