"""
FILE:         tests/unit/test_settings.py
WHAT IT DOES: Checks that settings load with sane defaults and honour environment overrides.
WHERE IT FITS: Phase 0 smoke test — proves the package installs, imports, and pytest is wired up.
"""

from prompt_engine.settings import PROJECT_ROOT, get_settings


# --- 1. Defaults point inside this repository ---
def test_settings_paths_live_inside_repository():
    settings = get_settings()
    assert settings.prompts_root == PROJECT_ROOT / "prompts"
    assert settings.prompts_root.is_dir()
    assert settings.results_dir.is_relative_to(PROJECT_ROOT)


# --- 2. Environment variables win over .env and defaults ---
def test_environment_variable_overrides_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example-host:9999/")
    get_settings.cache_clear()
    try:
        assert get_settings().ollama_base_url == "http://example-host:9999"  # trailing / stripped
    finally:
        get_settings.cache_clear()
