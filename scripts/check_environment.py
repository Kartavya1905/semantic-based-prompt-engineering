"""
FILE:         scripts/check_environment.py
WHAT IT DOES: Phase 0 readiness check — Python version, installed libraries, prompt folders,
              .env, the Ollama server, and whether the configured models are pulled.
WHERE IT FITS: Run once after setup and whenever something "mysteriously" fails.
USE:          python scripts/check_environment.py          (exit code 0 = ready, 1 = not ready)
"""

import importlib
import sys

import httpx

from prompt_engine.settings import PROJECT_ROOT, get_settings

REQUIRED_PYTHON = (3, 11)
CORE_LIBRARIES = ["pydantic", "jinja2", "yaml", "httpx", "dotenv"]
EVAL_LIBRARIES = ["pandas", "numpy", "sklearn", "statsmodels", "fastembed", "tabulate"]
REQUIRED_FOLDERS = [
    "prompts/system", "prompts/templates", "prompts/fragments", "prompts/manifests",
    "configs/experiments", "evaluation/golden_datasets", "evaluation/results", "tests/unit",
]


# --- 1. Tiny reporting helpers: every check prints one PASS / WARN / FAIL line ---
def report(status: str, check_name: str, detail: str = "") -> None:
    print(f"[{status:<4}] {check_name}{f' - {detail}' if detail else ''}")


def main() -> int:
    settings = get_settings()
    failed_checks = 0

    # --- 2. Python version ---
    if sys.version_info >= REQUIRED_PYTHON:
        report("PASS", "python", sys.version.split()[0])
    else:
        required_version = ".".join(map(str, REQUIRED_PYTHON))
        report("FAIL", "python", f"{sys.version.split()[0]} < {required_version}")
        failed_checks += 1

    # --- 3. Libraries: core is required, eval is required from Phase 5 on ---
    for library_name in CORE_LIBRARIES + EVAL_LIBRARIES:
        try:
            module = importlib.import_module(library_name)
            report("PASS", f"import {library_name}", getattr(module, "__version__", ""))
        except ImportError as import_error:
            report("FAIL", f"import {library_name}", str(import_error))
            failed_checks += 1

    # --- 4. Repository layout + local settings file ---
    for folder in REQUIRED_FOLDERS:
        if (PROJECT_ROOT / folder).is_dir():
            report("PASS", f"folder {folder}")
        else:
            report("FAIL", f"folder {folder}", "missing")
            failed_checks += 1
    if (PROJECT_ROOT / ".env").exists():
        report("PASS", ".env")
    else:
        report("WARN", ".env", "not found - using defaults (copy .env.example to .env)")

    # --- 5. Ollama server reachable, and which configured models are pulled ---
    try:
        tags_response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        tags_response.raise_for_status()
    except httpx.HTTPError as connection_error:
        report("FAIL", "ollama server", f"{settings.ollama_base_url} unreachable")
        print(f"       {connection_error}\n       Start Ollama (see README → Local LLM).")
        return 1

    version_response = httpx.get(f"{settings.ollama_base_url}/api/version", timeout=5.0)
    server_version = version_response.json()["version"]
    report("PASS", "ollama server", f"{settings.ollama_base_url} v{server_version}")
    pulled_models = {model["name"] for model in tags_response.json().get("models", [])}
    for model_name in (settings.default_model_name, settings.ci_model_name):
        if model_name in pulled_models:
            report("PASS", f"model {model_name}")
        else:
            report("FAIL", f"model {model_name}", f"not pulled - run: ollama pull {model_name}")
            failed_checks += 1

    print("\nREADY" if failed_checks == 0 else f"\nNOT READY ({failed_checks} failed checks)")
    return 0 if failed_checks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
