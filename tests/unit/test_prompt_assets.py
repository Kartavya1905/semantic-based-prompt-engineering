"""
FILE:         tests/unit/test_prompt_assets.py
WHAT IT DOES: Treats prompt files like code: every manifest, component, template and few-shot
              example is checked for validity, consistency and safety before any model sees it.
WHERE IT FITS: Phase 2. New manifests under prompts/manifests/ are picked up automatically.
"""

import importlib
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from jinja2 import meta, nodes
from pydantic import BaseModel, ValidationError

from prompt_engine.manifest_models import FewShotExample, PromptManifest
from prompt_engine.schemas import CONTRACTS_BY_PROMPT, validate_as_model_output
from prompt_engine.settings import get_settings
from prompt_engine.templating import build_template_environment

PROMPTS_ROOT = get_settings().prompts_root
MANIFEST_PATHS = sorted((PROMPTS_ROOT / "manifests").glob("*/*.yaml"))
MANIFEST_IDS = [f"{path.parent.name}/{path.stem}" for path in MANIFEST_PATHS]


# --- 1. Helpers ---------------------------------------------------------------------------------
def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> PromptManifest:
    return PromptManifest.model_validate(load_yaml(path))


def load_manifest_by_label(prompt_id: str, variant_label: str) -> PromptManifest:
    return load_manifest(PROMPTS_ROOT / "manifests" / prompt_id / f"{variant_label}.yaml")


def resolve_contract(schema_ref: str) -> tuple[ModuleType, type[BaseModel]]:
    module_path, class_name = schema_ref.split(":")
    contract_module = importlib.import_module(module_path)
    return contract_module, getattr(contract_module, class_name)


def parse_template(manifest: PromptManifest) -> nodes.Template:
    template_source = (PROMPTS_ROOT / manifest.human_template.source_path).read_text("utf-8")
    return build_template_environment().parse(template_source)


# --- 2. Manifests: valid, self-consistent, pointing at real files --------------------------------
def test_manifests_are_discovered():
    assert len(MANIFEST_PATHS) >= 3


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_manifest_prompt_id_matches_its_folder(manifest_path):
    assert load_manifest(manifest_path).prompt_id == manifest_path.parent.name


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_every_referenced_file_exists(manifest_path):
    manifest = load_manifest(manifest_path)
    referenced_paths = [component.source_path for component in manifest.system_components]
    referenced_paths.append(manifest.human_template.source_path)
    if manifest.few_shot:
        referenced_paths.append(manifest.few_shot.source_path)
    missing_paths = [path for path in referenced_paths if not (PROMPTS_ROOT / path).is_file()]
    assert not missing_paths


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_schema_ref_is_the_registered_contract(manifest_path):
    manifest = load_manifest(manifest_path)
    _, contract = resolve_contract(manifest.output_schema_ref)
    assert contract in CONTRACTS_BY_PROMPT[manifest.prompt_id]


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_manifest_major_version_tracks_schema_major_version(manifest_path):
    """Changing the output schema (MAJOR) forces every manifest using it to bump MAJOR too."""
    manifest = load_manifest(manifest_path)
    contract_module, _ = resolve_contract(manifest.output_schema_ref)
    assert manifest.version.split(".")[0] == contract_module.SCHEMA_VERSION.split(".")[0]


# --- 3. System components: static text only ------------------------------------------------------
@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_system_components_contain_no_template_syntax(manifest_path):
    """Variables in system text would break caching, diffing and the data/instruction boundary."""
    for component in load_manifest(manifest_path).system_components:
        component_text = (PROMPTS_ROOT / component.source_path).read_text(encoding="utf-8")
        assert component_text.strip(), f"{component.source_path} is empty"
        for jinja_marker in ("{{", "{%", "{#"):
            assert jinja_marker not in component_text, f"{jinja_marker} in {component.source_path}"


# --- 4. Human template: declared variables, all escaped -----------------------------------------
@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_template_variables_match_required_variables(manifest_path):
    manifest = load_manifest(manifest_path)
    used_variables = meta.find_undeclared_variables(parse_template(manifest))
    assert used_variables == set(manifest.human_template.required_variables)


@pytest.mark.parametrize("manifest_path", MANIFEST_PATHS, ids=MANIFEST_IDS)
def test_every_template_variable_is_xml_escaped(manifest_path):
    """Each {{ variable }} must be written {{ variable | xml_safe }}: prompt-injection defence."""
    template_ast = parse_template(load_manifest(manifest_path))
    all_variable_uses = [
        name_node.name
        for name_node in template_ast.find_all(nodes.Name)
        if name_node.ctx == "load"
    ]
    escaped_variable_uses = [
        filter_node.node.name
        for filter_node in template_ast.find_all(nodes.Filter)
        if filter_node.name == "xml_safe" and isinstance(filter_node.node, nodes.Name)
    ]
    assert sorted(all_variable_uses) == sorted(escaped_variable_uses)


# --- 5. Few-shot examples: valid answers, matching inputs ---------------------------------------
FEW_SHOT_MANIFEST_PATHS = [path for path in MANIFEST_PATHS if load_manifest(path).few_shot]


@pytest.mark.parametrize("manifest_path", FEW_SHOT_MANIFEST_PATHS, ids=lambda path: path.stem)
def test_few_shot_examples_obey_the_contract_and_template(manifest_path):
    manifest = load_manifest(manifest_path)
    assert manifest.few_shot is not None
    _, contract = resolve_contract(manifest.output_schema_ref)
    raw_examples = load_yaml(PROMPTS_ROOT / manifest.few_shot.source_path)
    examples = [FewShotExample.model_validate(raw_example) for raw_example in raw_examples]

    assert len(examples) >= manifest.few_shot.max_examples
    assert len({example.example_id for example in examples}) == len(examples)
    for example in examples:
        validate_as_model_output(contract, example.expected_output)  # raises if invalid
        assert set(example.input_variables) == set(manifest.human_template.required_variables)


# --- 6. Experiment hygiene: each variant changes exactly ONE factor versus the baseline ----------
def changed_fields(baseline: PromptManifest, variant: PromptManifest) -> set[str]:
    ignored_fields = {"version", "description"}
    baseline_fields, variant_fields = baseline.model_dump(), variant.model_dump()
    return {
        field_name
        for field_name in baseline_fields
        if field_name not in ignored_fields
        and baseline_fields[field_name] != variant_fields[field_name]
    }


def test_policy_first_variant_only_reorders_components():
    baseline = load_manifest_by_label("ticket_triage", "v1_baseline")
    variant = load_manifest_by_label("ticket_triage", "v2_policy_first")
    assert changed_fields(baseline, variant) == {"system_components"}
    component_key = lambda component: component.component_id  # noqa: E731
    assert sorted(baseline.system_components, key=component_key) == sorted(
        variant.system_components, key=component_key
    )


def test_fewshot_variant_only_adds_examples():
    baseline = load_manifest_by_label("ticket_triage", "v1_baseline")
    variant = load_manifest_by_label("ticket_triage", "v3_fewshot")
    assert changed_fields(baseline, variant) == {"few_shot"}


def test_explicit_critical_variant_only_swaps_the_policy_file():
    parent = load_manifest_by_label("ticket_triage", "v3_fewshot")
    variant = load_manifest_by_label("ticket_triage", "v4_explicit_critical")
    assert changed_fields(parent, variant) == {"system_components"}
    changed_components = [
        (parent_component.component_id, variant_component.source_path)
        for parent_component, variant_component
        in zip(parent.system_components, variant.system_components, strict=True)
        if parent_component != variant_component
    ]
    assert changed_components == [
        ("policy", "system/policies/escalation_policy_explicit_critical.md"),
    ]


def test_critical_example_variant_only_changes_examples():
    parent = load_manifest_by_label("ticket_triage", "v4_explicit_critical")
    variant = load_manifest_by_label("ticket_triage", "v5_critical_example")
    assert changed_fields(parent, variant) == {"few_shot"}


def test_extended_examples_keep_the_original_three_unchanged():
    """v5's file must start with v3's exact examples, so FS-004 is the only new factor."""
    original_examples = load_yaml(PROMPTS_ROOT / "fragments/ticket_triage/examples.yaml")
    extended_examples = load_yaml(
        PROMPTS_ROOT / "fragments/ticket_triage/examples_with_critical.yaml"
    )
    assert extended_examples[: len(original_examples)] == original_examples
    assert [example["example_id"] for example in extended_examples[len(original_examples):]] == [
        "FS-004",
    ]


TRIGGER_FIELDS = ("data_loss_reported", "security_exposure_reported", "full_outage_reported")


def test_trigger_variant_only_changes_the_contract_and_matching_examples():
    parent = load_manifest_by_label("ticket_triage", "v5_critical_example")
    variant = load_manifest_by_label("ticket_triage", "v6_critical_triggers")
    assert changed_fields(parent, variant) == {"output_schema_ref", "few_shot"}
    assert variant.few_shot is not None and parent.few_shot is not None
    assert variant.few_shot.max_examples == parent.few_shot.max_examples


def test_trigger_examples_are_v5_examples_plus_trigger_answers():
    """Same tickets, same labels, same order: only the three trigger answers are new."""
    v5_examples = load_yaml(PROMPTS_ROOT / "fragments/ticket_triage/examples_with_critical.yaml")
    v6_examples = load_yaml(PROMPTS_ROOT / "fragments/ticket_triage/examples_with_triggers.yaml")
    assert len(v6_examples) == len(v5_examples)
    for v5_example, v6_example in zip(v5_examples, v6_examples, strict=True):
        v6_answer_without_triggers = {
            key: value for key, value in v6_example["expected_output"].items()
            if key not in TRIGGER_FIELDS
        }
        assert v6_example["input_variables"] == v5_example["input_variables"]
        assert v6_answer_without_triggers == v5_example["expected_output"]
        assert set(TRIGGER_FIELDS) <= set(v6_example["expected_output"])


# --- 7. The manifest model itself rejects malformed recipes --------------------------------------
@pytest.fixture
def baseline_manifest_data() -> dict:
    return load_yaml(PROMPTS_ROOT / "manifests" / "ticket_triage" / "v1_baseline.yaml")


def test_misspelled_key_is_rejected(baseline_manifest_data):
    baseline_manifest_data["default_generation"]["temprature"] = 0.2
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        PromptManifest.model_validate(baseline_manifest_data)


def test_string_temperature_is_rejected(baseline_manifest_data):
    baseline_manifest_data["default_generation"]["temperature"] = "0.2"
    with pytest.raises(ValidationError):
        PromptManifest.model_validate(baseline_manifest_data)


def test_duplicate_xml_tag_is_rejected(baseline_manifest_data):
    baseline_manifest_data["system_components"][1]["xml_tag"] = "role"
    with pytest.raises(ValidationError, match="duplicate xml_tag"):
        PromptManifest.model_validate(baseline_manifest_data)


def test_reserved_xml_tag_is_rejected(baseline_manifest_data):
    baseline_manifest_data["system_components"][0]["xml_tag"] = "ticket"
    with pytest.raises(ValidationError, match="reserved"):
        PromptManifest.model_validate(baseline_manifest_data)
