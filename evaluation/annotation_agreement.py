"""
FILE:         evaluation/annotation_agreement.py
WHAT IT DOES: Second-annotator workflow for a golden dataset.
              1. export  → a BLIND spreadsheet (tickets only, no labels) for a second person
              2. compare → Cohen's kappa per field + a list of disagreements to adjudicate
WHERE IT FITS: Phase 5. Kappa ≥ 0.7 means the labelling rules are clear enough to trust;
              below that, fix ANNOTATION_GUIDELINE.md before blaming the prompt.
USE:          python -m evaluation.annotation_agreement export <dataset.jsonl> <sheet.csv>
              (fill in the label columns in LibreOffice / Excel / Google Sheets, save as CSV)
              python -m evaluation.annotation_agreement compare <dataset.jsonl> <sheet.csv>
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from evaluation.golden_case_model import GoldenCase, load_golden_cases

# Fields the second annotator labels. Entities and summaries are checked during adjudication.
LABELLED_FIELDS = ("category", "urgency", "requires_human_escalation")
TICKET_COLUMNS = ("case_id", "customer_tier", "ticket_subject", "ticket_body")
KAPPA_TRUST_THRESHOLD = 0.7


# --- 1. Export: tickets only. Showing the existing labels would bias the second annotator. ----
def export_blind_sheet(golden_cases: list[GoldenCase], sheet_path: Path) -> None:
    with sheet_path.open("w", encoding="utf-8-sig", newline="") as sheet_file:  # BOM: Excel-safe
        sheet_writer = csv.DictWriter(sheet_file, fieldnames=TICKET_COLUMNS + LABELLED_FIELDS)
        sheet_writer.writeheader()
        for case in golden_cases:
            sheet_writer.writerow({
                "case_id": case.case_id,
                **{column: case.input_variables[column] for column in TICKET_COLUMNS[1:]},
                **{field_name: "" for field_name in LABELLED_FIELDS},
            })


def read_sheet_labels(sheet_path: Path) -> dict[str, dict[str, str]]:
    with sheet_path.open(encoding="utf-8-sig", newline="") as sheet_file:
        return {
            row["case_id"]: {field_name: normalise_label(row[field_name])
                             for field_name in LABELLED_FIELDS}
            for row in csv.DictReader(sheet_file)
        }


def normalise_label(raw_label: str) -> str:
    """'True', 'yes', ' High ' → 'true', 'true', 'high': forgiving of spreadsheet habits."""
    cleaned_label = raw_label.strip().lower()
    return {"yes": "true", "y": "true", "1": "true", "no": "false", "n": "false",
            "0": "false"}.get(cleaned_label, cleaned_label)


# --- 2. Compare: chance-corrected agreement per field, plus every disagreement ----------------
@dataclass(frozen=True)
class FieldAgreement:
    field_name: str
    percent_agreement: float
    cohen_kappa: float | None  # None when kappa is undefined (both annotators used one label)


@dataclass(frozen=True)
class Disagreement:
    case_id: str
    field_name: str
    golden_label: str
    second_label: str


def compare_annotations(
    golden_cases: list[GoldenCase], second_labels: dict[str, dict[str, str]]
) -> tuple[list[FieldAgreement], list[Disagreement]]:
    missing_case_ids = [case.case_id for case in golden_cases if case.case_id not in second_labels]
    if missing_case_ids:
        raise ValueError(f"sheet has no labels for {missing_case_ids[:5]} (and maybe more)")
    unlabelled_case_ids = [
        case_id for case_id, labels in second_labels.items() if not all(labels.values())
    ]
    if unlabelled_case_ids:
        raise ValueError(f"empty label cells for {unlabelled_case_ids[:5]} (and maybe more)")

    field_agreements, disagreements = [], []
    for field_name in LABELLED_FIELDS:
        golden_column = [str(case.expected_output[field_name]).lower() for case in golden_cases]
        second_column = [second_labels[case.case_id][field_name] for case in golden_cases]
        matches = [
            golden == second for golden, second in zip(golden_column, second_column, strict=True)
        ]
        both_constant = len(set(golden_column) | set(second_column)) == 1
        field_agreements.append(FieldAgreement(
            field_name=field_name,
            percent_agreement=sum(matches) / len(matches),
            cohen_kappa=None if both_constant else float(
                cohen_kappa_score(golden_column, second_column)
            ),
        ))
        disagreements += [
            Disagreement(case.case_id, field_name, golden, second)
            for case, golden, second, matched
            in zip(golden_cases, golden_column, second_column, matches, strict=True)
            if not matched
        ]
    return field_agreements, disagreements


# --- 3. CLI --------------------------------------------------------------------------------------
def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("command", choices=["export", "compare"])
    argument_parser.add_argument("dataset_path", type=Path)
    argument_parser.add_argument("sheet_path", type=Path)
    argument_parser.add_argument("--split", choices=["dev", "test"])
    parsed_args = argument_parser.parse_args()
    golden_cases = load_golden_cases(parsed_args.dataset_path, split=parsed_args.split)

    if parsed_args.command == "export":
        export_blind_sheet(golden_cases, parsed_args.sheet_path)
        print(f"Wrote {len(golden_cases)} blind tickets to {parsed_args.sheet_path}")
        return 0

    field_agreements, disagreements = compare_annotations(
        golden_cases, read_sheet_labels(parsed_args.sheet_path)
    )
    for agreement in field_agreements:
        kappa_text = "n/a" if agreement.cohen_kappa is None else f"{agreement.cohen_kappa:.2f}"
        verdict = "OK" if (agreement.cohen_kappa or 0) >= KAPPA_TRUST_THRESHOLD else "LOW"
        print(f"{agreement.field_name:28} agreement={agreement.percent_agreement:.0%} "
              f"kappa={kappa_text} [{verdict}]")
    print(f"\n{len(disagreements)} disagreements to adjudicate:")
    for disagreement in disagreements:
        print(f"  {disagreement.case_id} {disagreement.field_name}: "
              f"golden={disagreement.golden_label} second={disagreement.second_label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
