"""
FILE:         src/prompt_engine/manifest_models.py
WHAT IT DOES: Pydantic models that validate the prompt ASSETS themselves: manifests (the recipe
              for one prompt version) and few-shot example files.
WHERE IT FITS: Phase 2. A manifest typo ("temprature: 0.2") fails loudly at load time instead of
              being silently ignored. The registry (Phase 3) loads YAML through these models.
USED BY:      registry.py, composer.py, tests/unit/test_prompt_assets.py
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- 1. Shared strictness: unknown keys are errors, no type coercion ("0.2" is not 0.2) ---------
ASSET_CONFIG = ConfigDict(extra="forbid", strict=True)

# Tags the composer generates itself (Phase 3); components may not claim them.
RESERVED_XML_TAGS = frozenset({"output_schema", "examples", "example", "input", "output",
                               "task", "ticket", "validation_errors"})


# --- 2. One system component: a Markdown file wrapped in one XML boundary tag ------------------
class SystemComponentSpec(BaseModel):
    model_config = ASSET_CONFIG

    component_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source_path: str = Field(description="Path relative to prompts/, e.g. system/personas/x.md")
    xml_tag: str = Field(pattern=r"^[a-z][a-z_]*$")


# --- 3. The human (user) turn: a Jinja2 template and the variables it needs -------------------
class HumanTemplateSpec(BaseModel):
    model_config = ASSET_CONFIG

    source_path: str
    required_variables: list[str] = Field(min_length=1)


# --- 4. Optional few-shot block ----------------------------------------------------------------
class FewShotSpec(BaseModel):
    model_config = ASSET_CONFIG

    source_path: str
    max_examples: int = Field(default=3, ge=1, le=10)


# --- 5. Sampling parameters (experiments override these per run) -------------------------------
class GenerationParams(BaseModel):
    model_config = ASSET_CONFIG

    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    seed: int | None = None
    max_output_tokens: int = Field(default=512, gt=0)


# --- 6. The manifest = one prompt version --------------------------------------------------------
class PromptManifest(BaseModel):
    model_config = ASSET_CONFIG

    prompt_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", description="semver; MAJOR = schema major")
    description: str = Field(min_length=10, description="What this variant changes, and why")
    system_components: list[SystemComponentSpec] = Field(min_length=1)
    human_template: HumanTemplateSpec
    few_shot: FewShotSpec | None = None
    output_schema_ref: str = Field(pattern=r"^[\w.]+:\w+$", description="module.path:ClassName")
    default_generation: GenerationParams

    @model_validator(mode="after")
    def components_have_unique_ids_and_tags(self) -> "PromptManifest":
        component_ids = [component.component_id for component in self.system_components]
        xml_tags = [component.xml_tag for component in self.system_components]
        if len(set(component_ids)) != len(component_ids):
            raise ValueError(f"duplicate component_id in {component_ids}")
        if len(set(xml_tags)) != len(xml_tags):
            raise ValueError(f"duplicate xml_tag in {xml_tags}")
        reserved_tags_used = RESERVED_XML_TAGS.intersection(xml_tags)
        if reserved_tags_used:
            raise ValueError(f"xml_tag reserved for the composer: {sorted(reserved_tags_used)}")
        return self


# --- 7. One few-shot example (an entry in prompts/fragments/<prompt_id>/examples.yaml) ----------
class FewShotExample(BaseModel):
    model_config = ASSET_CONFIG

    example_id: str
    # For humans only: why this example exists. Never rendered into the prompt.
    teaching_point: str = Field(min_length=10)
    input_variables: dict[str, str]
    expected_output: dict[str, Any] = Field(description="Validated against the output contract")
