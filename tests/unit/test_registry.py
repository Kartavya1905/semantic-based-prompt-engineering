"""
FILE:         tests/unit/test_registry.py
WHAT IT DOES: Checks the registry finds, validates and safely reads prompt assets.
WHERE IT FITS: Phase 3. Uses the real prompts/ folder, plus throwaway folders for failure cases.
"""

import shutil

import pytest

from prompt_engine.manifest_models import FewShotSpec
from prompt_engine.registry import PromptAssetError, PromptRegistry
from prompt_engine.schemas.ticket_triage import TicketTriageResult
from prompt_engine.settings import get_settings


@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry()


# --- 1. Discovery and loading -------------------------------------------------------------------
def test_lists_all_ticket_triage_variants(registry):
    assert registry.list_variants("ticket_triage") == [
        "v1_baseline", "v2_policy_first", "v3_fewshot", "v4_explicit_critical",
        "v5_critical_example", "v6_critical_triggers",
    ]


def test_unknown_prompt_id_has_no_variants(registry):
    assert registry.list_variants("does_not_exist") == []


def test_loads_and_caches_manifest(registry):
    first_load = registry.load_manifest("ticket_triage", "v1_baseline")
    assert first_load.prompt_id == "ticket_triage"
    assert registry.load_manifest("ticket_triage", "v1_baseline") is first_load


def test_missing_variant_raises_clear_error(registry):
    with pytest.raises(PromptAssetError, match="not found"):
        registry.load_manifest("ticket_triage", "v9_missing")


def test_resolves_output_schema(registry):
    schema_ref = "prompt_engine.schemas.ticket_triage:TicketTriageResult"
    assert registry.resolve_output_schema(schema_ref) is TicketTriageResult


@pytest.mark.parametrize(
    "bad_schema_ref",
    ["prompt_engine.schemas.ticket_triage:NoSuchClass", "no_such_module:Thing",
     "prompt_engine.schemas.ticket_triage:SCHEMA_VERSION"],
)
def test_bad_schema_ref_raises_clear_error(registry, bad_schema_ref):
    with pytest.raises(PromptAssetError):
        registry.resolve_output_schema(bad_schema_ref)


def test_few_shot_loader_returns_first_n_examples(registry):
    spec = FewShotSpec(source_path="fragments/ticket_triage/examples.yaml", max_examples=2)
    assert [example.example_id for example in registry.load_few_shot_examples(spec)] == [
        "FS-001", "FS-002",
    ]


def test_few_shot_loader_rejects_asking_for_too_many(registry):
    spec = FewShotSpec(source_path="fragments/ticket_triage/examples.yaml", max_examples=10)
    with pytest.raises(PromptAssetError, match="has 3 examples"):
        registry.load_few_shot_examples(spec)


# --- 2. Safety: assets can only come from inside prompts/ ---------------------------------------
def test_path_traversal_is_refused(registry):
    with pytest.raises(PromptAssetError, match="outside"):
        registry.read_asset("../pyproject.toml")


def test_manifest_in_wrong_folder_is_rejected(tmp_path):
    copied_root = tmp_path / "prompts"
    shutil.copytree(get_settings().prompts_root, copied_root)
    misplaced_dir = copied_root / "manifests" / "other_prompt"
    misplaced_dir.mkdir()
    shutil.copy(copied_root / "manifests" / "ticket_triage" / "v1_baseline.yaml", misplaced_dir)

    with pytest.raises(PromptAssetError, match="declares prompt_id='ticket_triage'"):
        PromptRegistry(copied_root).load_manifest("other_prompt", "v1_baseline")
