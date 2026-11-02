"""
FILE:         src/prompt_engine/__init__.py
WHAT IT DOES: Marks prompt_engine as a package — the orchestration layer that loads prompt
              manifests, composes boundary-delimited messages, calls the LLM, and validates
              output against Pydantic contracts.
WHERE IT FITS: Everything under src/ is code; everything under prompts/ is data it reads.
"""

__version__ = "0.1.0"
