"""
FILE:         evaluation/metrics.py
WHAT IT DOES: Marks ONE pipeline answer against ONE golden case, producing a flat dict of scores
              (one row in the results file). Also scores summaries by meaning with local
              sentence embeddings.
WHERE IT FITS: Phase 6. The benchmark runner calls score_case() for every run; analysis
              (Phase 7) averages these rows per prompt variant / model / temperature.
"""

from pathlib import Path
from typing import Any

import numpy as np

from evaluation.golden_case_model import GoldenCase
from prompt_engine.pipeline import PipelineOutcome
from prompt_engine.schemas import CONTRACTS_BY_PROMPT
from prompt_engine.schemas.ticket_triage import UrgencyLevel
from prompt_engine.settings import PROJECT_ROOT

URGENCY_ORDER = [level.value for level in UrgencyLevel]  # low < medium < high < critical
RAW_TEXT_LIMIT = 2000  # keep result rows small; enough to debug a failure


# --- 1. Entity matching: exact (type, value) pairs, case-insensitive ----------------------------
def entity_set_scores(
    predicted_entities: list[dict[str, str]], expected_entities: list[dict[str, str]]
) -> dict[str, float]:
    def as_keys(entities: list[dict[str, str]]) -> set[tuple[str, str]]:
        return {(item["entity_type"], item["entity_value"].strip().lower()) for item in entities}

    predicted_keys, expected_keys = as_keys(predicted_entities), as_keys(expected_entities)
    if not predicted_keys and not expected_keys:
        return {"entity_precision": 1.0, "entity_recall": 1.0, "entity_f1": 1.0}
    true_positives = len(predicted_keys & expected_keys)
    precision = true_positives / len(predicted_keys) if predicted_keys else 0.0
    recall = true_positives / len(expected_keys) if expected_keys else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"entity_precision": precision, "entity_recall": recall, "entity_f1": f1}


# --- 2. Score one case ------------------------------------------------------------------------
def score_case(golden_case: GoldenCase, outcome: PipelineOutcome) -> dict[str, Any]:
    expected = golden_case.expected_output
    first_attempt = outcome.attempts[0]
    row: dict[str, Any] = {
        # 2a. What the answer key says
        "expected_category": expected["category"],
        "expected_urgency": expected["urgency"],
        "expected_escalation": expected["requires_human_escalation"],
        # 2b. Structural quality: did the guardrails have to step in?
        "schema_valid": outcome.is_valid,
        "first_pass_valid": outcome.first_pass_valid,
        "attempts_used": outcome.attempts_used,
        "first_attempt_error_types": sorted(
            {error["type"] for error in first_attempt.validation_errors or []}
        ),
        "finish_reasons": [attempt.finish_reason for attempt in outcome.attempts],
        "total_latency_ms": outcome.total_latency_ms,
        "prompt_tokens_first_attempt": first_attempt.prompt_tokens,
        "total_tokens": outcome.total_tokens,
        "final_raw_text": outcome.attempts[-1].raw_text[:RAW_TEXT_LIMIT],
    }

    # 2c. No valid answer: every quality metric scores as wrong (the system failed the ticket)
    if outcome.parsed_output is None:
        return row | {
            "predicted_category": None, "predicted_urgency": None, "predicted_escalation": None,
            "predicted_summary": None, "confidence_score": None,
            "category_correct": False, "urgency_correct": False, "escalation_correct": False,
            "all_labels_correct": False, "urgency_distance": None, "under_triaged": None,
            "entity_precision": 0.0, "entity_recall": 0.0, "entity_f1": 0.0,
            "model_proposed_urgency": None, "critical_trigger_found": None,
            "urgency_set_by_rule": None,
        }

    # 2d. Valid answer: compare field by field. Any ticket_triage contract works (v1 or v2):
    # both expose the same decision fields, and v2's urgency already has rule 1 applied.
    if not isinstance(outcome.parsed_output, CONTRACTS_BY_PROMPT["ticket_triage"]):
        raise TypeError(f"not a ticket_triage contract: {type(outcome.parsed_output).__name__}")
    answer: Any = outcome.parsed_output
    category_correct = answer.category.value == expected["category"]
    urgency_correct = answer.urgency.value == expected["urgency"]
    escalation_correct = answer.requires_human_escalation == expected["requires_human_escalation"]
    # Positive = over-triaged (too urgent, wastes time); negative = UNDER-triaged (dangerous).
    urgency_distance = (
        URGENCY_ORDER.index(answer.urgency.value) - URGENCY_ORDER.index(expected["urgency"])
    )
    predicted_entities = [entity.model_dump(mode="json") for entity in answer.extracted_entities]

    return row | {
        "predicted_category": answer.category.value,
        "predicted_urgency": answer.urgency.value,
        "predicted_escalation": answer.requires_human_escalation,
        "predicted_summary": answer.summary,
        "confidence_score": answer.confidence_score,
        "category_correct": category_correct,
        "urgency_correct": urgency_correct,
        "escalation_correct": escalation_correct,
        "all_labels_correct": category_correct and urgency_correct and escalation_correct,
        "urgency_distance": urgency_distance,
        "under_triaged": urgency_distance < 0,
        **entity_set_scores(predicted_entities, expected["extracted_entities"]),
        # 2e. v2 contract only (None for v1): did the model or the rule choose the urgency?
        "model_proposed_urgency": (
            answer.model_proposed_urgency.value
            if getattr(answer, "model_proposed_urgency", None) is not None else None
        ),
        "critical_trigger_found": getattr(answer, "critical_trigger_found", None),
        "urgency_set_by_rule": getattr(answer, "urgency_set_by_rule", None),
    }


# --- 3. Summary quality by meaning: cosine similarity of local sentence embeddings -------------
# fastembed runs a small ONNX model on the CPU: no GPU, no API key, no cost. The model downloads
# once (~90 MB) into .cache/fastembed (gitignored).
class SummarySimilarityScorer:
    def __init__(self, embedding_model_name: str, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding  # imported lazily: tests that skip it stay fast

        self.embedding_model = TextEmbedding(
            model_name=embedding_model_name,
            cache_dir=str(cache_dir or PROJECT_ROOT / ".cache" / "fastembed"),
        )

    def similarity(self, candidate_summary: str, reference_summary: str) -> float:
        candidate_vector, reference_vector = (
            vector / np.linalg.norm(vector)
            for vector in self.embedding_model.embed([candidate_summary, reference_summary])
        )
        return float(candidate_vector @ reference_vector)
