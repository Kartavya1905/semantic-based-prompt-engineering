"""
FILE:         src/prompt_engine/registry.py
WHAT IT DOES: Finds and loads prompt assets from prompts/: manifests (validated), component text,
              templates, few-shot examples, and the output contract a manifest points to.
WHERE IT FITS: Phase 3. The ONLY code that touches files under prompts/. The composer asks the
              registry for content and never opens files itself.
USED BY:      composer.py, scripts/render_prompt.py, the benchmark runner (Phase 6)
"""

import importlib
from pathlib import Path

import yaml
from pydantic import BaseModel

from prompt_engine.manifest_models import FewShotExample, FewShotSpec, PromptManifest
from prompt_engine.settings import get_settings


class PromptAssetError(Exception):
    """A prompt asset is missing, outside prompts/, or points at something that does not exist."""


class PromptRegistry:
    # --- 1. Setup: where assets live, plus small caches (one benchmark composes thousands) ------
    def __init__(self, prompts_root: Path | None = None) -> None:
        self.prompts_root = (prompts_root or get_settings().prompts_root).resolve()
        self._asset_text_cache: dict[str, str] = {}
        self._manifest_cache: dict[tuple[str, str], PromptManifest] = {}

    # --- 2. Discover which variants exist for a prompt ------------------------------------------
    def list_variants(self, prompt_id: str) -> list[str]:
        manifest_dir = self.prompts_root / "manifests" / prompt_id
        return sorted(manifest_path.stem for manifest_path in manifest_dir.glob("*.yaml"))

    # --- 3. Load one manifest, validated by PromptManifest --------------------------------------
    def load_manifest(self, prompt_id: str, variant_label: str) -> PromptManifest:
        cache_key = (prompt_id, variant_label)
        if cache_key not in self._manifest_cache:
            relative_path = f"manifests/{prompt_id}/{variant_label}.yaml"
            manifest = PromptManifest.model_validate(yaml.safe_load(self.read_asset(relative_path)))
            if manifest.prompt_id != prompt_id:
                raise PromptAssetError(
                    f"{relative_path} declares prompt_id={manifest.prompt_id!r}, "
                    f"expected {prompt_id!r}"
                )
            self._manifest_cache[cache_key] = manifest
        return self._manifest_cache[cache_key]

    # --- 4. Read any asset as text, refusing paths that escape prompts/ -------------------------
    def read_asset(self, relative_path: str) -> str:
        if relative_path not in self._asset_text_cache:
            asset_path = (self.prompts_root / relative_path).resolve()
            if not asset_path.is_relative_to(self.prompts_root):
                raise PromptAssetError(f"{relative_path!r} points outside {self.prompts_root}")
            if not asset_path.is_file():
                raise PromptAssetError(f"prompt asset not found: {relative_path}")
            self._asset_text_cache[relative_path] = asset_path.read_text(encoding="utf-8").strip()
        return self._asset_text_cache[relative_path]

    # --- 5. Few-shot examples: the first max_examples entries, validated ------------------------
    def load_few_shot_examples(self, few_shot_spec: FewShotSpec) -> list[FewShotExample]:
        raw_examples = yaml.safe_load(self.read_asset(few_shot_spec.source_path))
        examples = [FewShotExample.model_validate(raw_example) for raw_example in raw_examples]
        if len(examples) < few_shot_spec.max_examples:
            raise PromptAssetError(
                f"{few_shot_spec.source_path} has {len(examples)} examples, "
                f"manifest asks for {few_shot_spec.max_examples}"
            )
        return examples[: few_shot_spec.max_examples]

    # --- 6. Turn "module.path:ClassName" into the Pydantic contract class -----------------------
    @staticmethod
    def resolve_output_schema(schema_ref: str) -> type[BaseModel]:
        module_path, class_name = schema_ref.split(":")
        try:
            contract = getattr(importlib.import_module(module_path), class_name)
        except (ImportError, AttributeError) as lookup_error:
            message = f"cannot resolve output_schema_ref {schema_ref!r}"
            raise PromptAssetError(message) from lookup_error
        if not (isinstance(contract, type) and issubclass(contract, BaseModel)):
            raise PromptAssetError(f"{schema_ref!r} is not a Pydantic model")
        return contract
