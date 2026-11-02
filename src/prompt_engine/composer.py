"""
FILE:         src/prompt_engine/composer.py
WHAT IT DOES: Snaps a manifest's bricks together into the final two messages sent to the model:
              a SYSTEM message (components + schema + examples, each in its own XML tag) and a
              HUMAN message (the rendered ticket template).
WHERE IT FITS: Phase 3. Pure function of (manifest, ticket, overrides): no network, no randomness,
              so the same inputs always give byte-identical prompts.
USED BY:      the guardrail pipeline (Phase 4), the benchmark runner (Phase 6),
              scripts/render_prompt.py
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from jinja2 import Template
from pydantic import BaseModel

from prompt_engine.manifest_models import FewShotSpec, GenerationParams, PromptManifest
from prompt_engine.registry import PromptRegistry
from prompt_engine.schemas import validate_as_model_output
from prompt_engine.templating import build_template_environment, xml_safe


# --- 1. The result: everything the pipeline needs, frozen so nothing changes it later -----------
@dataclass(frozen=True)
class ComposedPrompt:
    prompt_id: str
    manifest_version: str
    system_message: str
    human_message: str
    output_schema: type[BaseModel]
    generation_params: GenerationParams
    # Hash of the parts that are the SAME for every ticket (system message + template source).
    # Equal fingerprints = same prompt; any wording edit changes it, even without a version bump.
    # Sampling parameters are deliberately excluded: a temperature sweep keeps one fingerprint.
    prompt_fingerprint: str

    def as_messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": self.human_message},
        ]


class PromptComposer:
    def __init__(self, registry: PromptRegistry | None = None) -> None:
        self.registry = registry or PromptRegistry()
        self.template_environment = build_template_environment()
        self._compiled_templates: dict[str, Template] = {}

    # --- 2. Main entry point --------------------------------------------------------------------
    def compose(
        self,
        manifest: PromptManifest,
        input_variables: dict[str, Any],
        generation_overrides: dict[str, Any] | None = None,
    ) -> ComposedPrompt:
        self._check_input_variables(manifest, input_variables)
        output_schema = self.registry.resolve_output_schema(manifest.output_schema_ref)

        system_message = self._build_system_message(manifest, output_schema)
        template_source = self.registry.read_asset(manifest.human_template.source_path)
        human_message = self._render_template(template_source, input_variables)

        # Overrides (e.g. temperature from an experiment) are re-validated with the same rules.
        generation_params = GenerationParams.model_validate(
            manifest.default_generation.model_dump() | (generation_overrides or {})
        )
        fingerprint_source = f"{system_message}\x00{template_source}".encode()

        return ComposedPrompt(
            prompt_id=manifest.prompt_id,
            manifest_version=manifest.version,
            system_message=system_message,
            human_message=human_message,
            output_schema=output_schema,
            generation_params=generation_params,
            prompt_fingerprint=hashlib.sha256(fingerprint_source).hexdigest()[:12],
        )

    # --- 3. Inputs must match the manifest exactly: nothing missing, nothing unexpected ---------
    @staticmethod
    def _check_input_variables(manifest: PromptManifest, input_variables: dict[str, Any]) -> None:
        required_variables = set(manifest.human_template.required_variables)
        missing_variables = required_variables - input_variables.keys()
        unexpected_variables = input_variables.keys() - required_variables
        if missing_variables:
            raise ValueError(f"missing template variables: {sorted(missing_variables)}")
        if unexpected_variables:
            raise ValueError(f"unexpected template variables: {sorted(unexpected_variables)}")

    # --- 4. System message: static content only, in a fixed order -------------------------------
    # Order: manifest components → <output_schema> → <examples>.
    # Everything here is identical for every ticket, which also lets the model server reuse its
    # cached computation for this prefix across requests.
    def _build_system_message(
        self, manifest: PromptManifest, output_schema: type[BaseModel]
    ) -> str:
        system_sections = [
            wrap_in_tag(component.xml_tag, self.registry.read_asset(component.source_path))
            for component in manifest.system_components
        ]
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2, ensure_ascii=False)
        system_sections.append(wrap_in_tag("output_schema", schema_json))
        if manifest.few_shot is not None:
            system_sections.append(self._render_examples(manifest.few_shot, output_schema))
        return "\n\n".join(system_sections)

    # --- 5. Few-shot block: each answer is re-validated, then printed in contract field order ---
    def _render_examples(self, few_shot_spec: FewShotSpec, output_schema: type[BaseModel]) -> str:
        rendered_examples = []
        for example in self.registry.load_few_shot_examples(few_shot_spec):
            validated_answer = validate_as_model_output(output_schema, example.expected_output)
            example_input = xml_safe(json.dumps(example.input_variables, ensure_ascii=False))
            rendered_examples.append(
                "<example>\n"
                f"<input>{example_input}</input>\n"
                f"<output>{validated_answer.model_dump_json()}</output>\n"
                "</example>"
            )
        return wrap_in_tag("examples", "\n".join(rendered_examples))

    # --- 6. Human message: compiled once per template, rendered per ticket ----------------------
    def _render_template(self, template_source: str, input_variables: dict[str, Any]) -> str:
        if template_source not in self._compiled_templates:
            self._compiled_templates[template_source] = self.template_environment.from_string(
                template_source
            )
        return self._compiled_templates[template_source].render(**input_variables).strip()


def wrap_in_tag(xml_tag: str, content: str) -> str:
    return f"<{xml_tag}>\n{content}\n</{xml_tag}>"
