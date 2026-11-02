"""
FILE:         src/prompt_engine/settings.py
WHAT IT DOES: Reads local settings (.env + environment variables) into one typed, frozen object.
WHERE IT FITS: Single source of truth for URLs, model names and paths.
              Nothing else in the project reads os.environ directly.
USED BY:      clients (Ollama URL), evaluation (results dir, embedding model), scripts.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# --- 1. Locate the repository root (src/prompt_engine/settings.py → up two levels) ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# --- 2. The settings object: one field per .env key, with safe local defaults ---
@dataclass(frozen=True)
class EngineSettings:
    ollama_base_url: str
    default_model_name: str
    ci_model_name: str
    embedding_model_name: str
    results_dir: Path
    prompts_root: Path


# --- 3. Load once per process: .env fills in anything not already set in the environment ---
@lru_cache(maxsize=1)
def get_settings() -> EngineSettings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return EngineSettings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        default_model_name=os.getenv("DEFAULT_MODEL_NAME", "qwen2.5:7b"),
        ci_model_name=os.getenv("CI_MODEL_NAME", "qwen2.5:1.5b"),
        embedding_model_name=os.getenv(
            "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        results_dir=PROJECT_ROOT / os.getenv("RESULTS_DIR", "evaluation/results"),
        prompts_root=PROJECT_ROOT / "prompts",
    )
